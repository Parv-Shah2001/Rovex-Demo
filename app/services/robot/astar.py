"""
File: app/services/robot/astar.py
Description: Implements the A* (A-Star) search algorithm for hospital stretcher robots.
Computes optimal macro routes across a weighted coordinate graph. The edge weights can be 
dynamically adjusted to avoid high-congestion corridors, and the solver returns step-by-step
traversal details so the frontend can visualize exactly how the algorithm works.
"""

import math
import heapq
import logging
from typing import List, Dict, Any, Tuple, Optional, Set

from app.core.config import DEFAULT_NODES, DEFAULT_EDGES

logger = logging.getLogger("rovex.astar")


class HospitalGraph:
    """
    Manages the physical hospital layout graph, consisting of nodes with 2D coordinates 
    (in meters) and bidirectional edges with numeric transit weights.
    """
    def __init__(self):
        # Nodes: { "NodeName": { "x": float, "y": float, "description": str } }
        self.nodes: Dict[str, Dict[str, Any]] = dict(DEFAULT_NODES)
        
        # Edges: { "NodeA": { "NodeB": weight } }
        self.edges: Dict[str, Dict[str, float]] = {}
        for node in self.nodes:
            self.edges[node] = {}
            
        for edge in DEFAULT_EDGES:
            n1, n2, w = edge["from"], edge["to"], edge["weight"]
            if n1 in self.nodes and n2 in self.nodes:
                self.edges[n1][n2] = w
                self.edges[n2][n1] = w  # Bidirectional

    def get_nodes(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns all nodes in the graph.
        """
        return self.nodes

    def get_edges(self) -> List[Dict[str, Any]]:
        """
        Returns a flat list of edges for reporting or editing.
        """
        flat_edges = []
        visited = set()
        for node_a, connections in self.edges.items():
            for node_b, weight in connections.items():
                edge_key = tuple(sorted([node_a, node_b]))
                if edge_key not in visited:
                    visited.add(edge_key)
                    flat_edges.append({
                        "from": node_a,
                        "to": node_b,
                        "weight": weight
                    })
        return flat_edges

    def update_edge_weight(self, node_a: str, node_b: str, new_weight: float) -> bool:
        """
        Updates the weight/cost of the edge connecting node_a and node_b.
        Returns True if successful, False if the edge does not exist.
        """
        if node_a in self.edges and node_b in self.edges[node_a]:
            self.edges[node_a][node_b] = new_weight
            self.edges[node_b][node_a] = new_weight
            logger.info(f"Graph weight updated: [{node_a} <-> {node_b}] = {new_weight}")
            return True
        logger.warning(f"Failed to update weight: Edge [{node_a} <-> {node_b}] does not exist.")
        return False

    def get_distance(self, node_a: str, node_b: str) -> float:
        """
        Computes straight-line Euclidean distance between two nodes (used as heuristic h(n)).
        """
        pos_a = self.nodes[node_a]
        pos_b = self.nodes[node_b]
        return math.sqrt((pos_a["x"] - pos_b["x"])**2 + (pos_a["y"] - pos_b["y"])**2)


# Instantiate the active singleton graph representing the physical floor map
hospital_map = HospitalGraph()


def plan_astar_path(start: str, goal: str, graph: HospitalGraph = hospital_map) -> Optional[Dict[str, Any]]:
    """
    Finds the shortest path between a start node and goal node using the A* algorithm.
    
    Heuristic function h(n) = Euclidean distance between node 'n' and 'goal'.
    Cost function g(n) = Sum of edge weights from 'start' to 'n'.
    Priority metric f(n) = g(n) + h(n).
    
    Returns:
        Dict: Path list, total distance, total cost, and execution steps (for visual output)
        None: If no path can be established.
    """
    if start not in graph.nodes or goal not in graph.nodes:
        logger.error(f"Cannot run A*: Invalid nodes [{start}] or [{goal}]")
        return None
        
    # Heap queue stores: (f_score, current_node_name)
    open_set: List[Tuple[float, str]] = []
    heapq.heappush(open_set, (graph.get_distance(start, goal), start))
    
    # Track the node we came from to reconstruct the path
    came_from: Dict[str, str] = {}
    
    # g_score: actual cost from start to current node
    g_score: Dict[str, float] = {node: float('inf') for node in graph.nodes}
    g_score[start] = 0.0
    
    # f_score: total estimated cost (g_score + h_score)
    f_score: Dict[str, float] = {node: float('inf') for node in graph.nodes}
    f_score[start] = graph.get_distance(start, goal)
    
    # For visualization of algorithm execution
    steps_log: List[Dict[str, Any]] = []
    visited_nodes: List[str] = []
    
    while open_set:
        # Get the node with lowest f_score
        current_f, current = heapq.heappop(open_set)
        visited_nodes.append(current)
        
        # Log current step details
        steps_log.append({
            "current_node": current,
            "g_score": g_score[current],
            "f_score": current_f,
            "heuristic": graph.get_distance(current, goal),
            "open_list": [item[1] for item in open_set]
        })
        
        # Reached the goal! Reconstruct path
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            
            # Compute total actual physical distance (sum of Euclid segments)
            tot_dist = 0.0
            for i in range(len(path) - 1):
                tot_dist += graph.get_distance(path[i], path[i+1])
                
            return {
                "path": path,
                "total_cost": g_score[goal],
                "total_distance_meters": round(tot_dist, 2),
                "steps_taken": len(visited_nodes),
                "visited_nodes": visited_nodes,
                "algorithm_steps": steps_log
            }
            
        # Inspect neighbors
        for neighbor, weight in graph.edges[current].items():
            tentative_g_score = g_score[current] + weight
            
            if tentative_g_score < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g_score
                f_score[neighbor] = tentative_g_score + graph.get_distance(neighbor, goal)
                
                # Check if already in queue (simplified heapq logic)
                if not any(item[1] == neighbor for item in open_set):
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))
                    
    logger.warning(f"A* search completed with no path from [{start}] to [{goal}].")
    return None
