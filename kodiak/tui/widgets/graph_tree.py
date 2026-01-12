"""
GraphTree Widget

A widget that renders the attack surface as a navigable tree structure.
Supports expand/collapse, navigation, and selection with node type icons.
"""

from typing import Optional, List, Dict, Set, Any
from textual.widget import Widget
from textual.widgets import Tree, Static
from textual.containers import Vertical
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.message import Message

from kodiak.tui.state import app_state, ScanState
from kodiak.database.models import Node


class NodeSelected(Message):
    """Message sent when a node is selected"""
    
    def __init__(self, node_id: str, node_data: Dict[str, Any]) -> None:
        super().__init__()
        self.node_id = node_id
        self.node_data = node_data


class GraphTreeNode:
    """Wrapper for tree node data"""
    
    def __init__(self, node: Node):
        self.node = node
        self.children: List[GraphTreeNode] = []
        self.parent: Optional[GraphTreeNode] = None
        self.expanded = False
    
    @property
    def id(self) -> str:
        return str(self.node.id)
    
    @property
    def label(self) -> str:
        """Get the display label for this node"""
        icon = self._get_node_icon()
        name = self.node.name or "Unknown"
        
        # Add severity indicator for vulnerabilities
        if self.node.type == "vulnerability" and self.node.properties.get('severity'):
            severity_icon = self._get_severity_icon(self.node.properties['severity'])
            return f"{icon} {name} {severity_icon}"
        
        return f"{icon} {name}"
    
    def _get_node_icon(self) -> str:
        """Get the appropriate icon for node type"""
        node_icons = {
            "target": "🎯",        # Target
            "domain": "🌐",        # Domain
            "ip": "📡",            # IP/Host
            "port": "🔌",          # Port
            "service": "⚙️",       # Service
            "url": "🌐",           # URL/Endpoint
            "parameter": "📝",     # Parameter
            "vulnerability": "🔓", # Vulnerability
            "credential": "🔑",    # Credential
            "file": "📄",          # File
            "directory": "📁",     # Directory
            "technology": "🔧",    # Technology
        }
        return node_icons.get(self.node.type, "❓")
    
    def _get_severity_icon(self, severity: str) -> str:
        """Get severity color indicator"""
        severity_icons = {
            "critical": "🔴",  # Red circle
            "high": "🟠",      # Orange circle
            "medium": "🟡",    # Yellow circle
            "low": "🟢",       # Green circle
            "info": "🔵",      # Blue circle
        }
        return severity_icons.get(severity.lower(), "⚪")
    
    def add_child(self, child: 'GraphTreeNode'):
        """Add a child node"""
        child.parent = self
        self.children.append(child)
    
    def remove_child(self, child: 'GraphTreeNode'):
        """Remove a child node"""
        if child in self.children:
            child.parent = None
            self.children.remove(child)
    
    def get_path(self) -> List[str]:
        """Get the path from root to this node"""
        path = []
        current = self
        while current:
            path.insert(0, current.id)
            current = current.parent
        return path


class GraphTree(Widget):
    """
    Tree widget that displays the attack surface graph.
    Supports navigation, selection, and expand/collapse.
    """
    
    DEFAULT_CSS = """
    GraphTree {
        border: solid $primary;
        height: 100%;
        min-height: 10;
    }
    
    GraphTree > Vertical {
        height: 100%;
    }
    
    GraphTree .title {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        text-align: center;
        text-style: bold;
    }
    
    GraphTree Tree {
        height: 1fr;
        border: none;
    }
    
    GraphTree .empty {
        height: 100%;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    
    GraphTree .vulnerability {
        color: $error;
    }
    
    GraphTree .critical {
        color: $error;
        text-style: bold;
    }
    
    GraphTree .high {
        color: $warning;
        text-style: bold;
    }
    
    GraphTree .medium {
        color: $warning;
    }
    
    GraphTree .low {
        color: $success;
    }
    """
    
    # Reactive properties
    current_scan: reactive[Optional[ScanState]] = reactive(None)
    nodes: reactive[List[Node]] = reactive([])
    selected_node_id: reactive[Optional[str]] = reactive(None)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tree_nodes: Dict[str, GraphTreeNode] = {}
        self.root_nodes: List[GraphTreeNode] = []
        
        # Subscribe to state changes
        app_state.subscribe("current_scan_changed", self._on_scan_changed)
        app_state.subscribe("node_added", self._on_node_added)
    
    def compose(self) -> ComposeResult:
        """Compose the graph tree layout"""
        with Vertical():
            yield Static("Attack Surface", classes="title", id="title")
            yield Tree("Root", id="graph-tree")
    
    def on_mount(self) -> None:
        """Initialize graph tree when mounted"""
        self.current_scan = app_state.get_current_scan()
        self._refresh_tree()
    
    def _on_scan_changed(self, event):
        """Handle scan change events"""
        self.current_scan = app_state.get_current_scan()
        self._refresh_tree()
    
    def _on_node_added(self, event):
        """Handle node added events"""
        data = event.data
        if self.current_scan and data.get("scan_id") == self.current_scan.id:
            node = data.get("node")
            if node:
                self._add_node_to_tree(node)
    
    def _refresh_tree(self):
        """Refresh the entire tree"""
        tree = self.query_one("#graph-tree", Tree)
        tree.clear()
        
        self.tree_nodes.clear()
        self.root_nodes.clear()
        
        if not self.current_scan:
            self.nodes = []
            tree.root.add("No scan selected")
            return
        
        # Get nodes from current scan
        nodes = app_state.get_nodes_for_scan(self.current_scan.id)
        self.nodes = nodes
        
        if not nodes:
            tree.root.add("No nodes discovered yet")
            return
        
        # Build tree structure
        self._build_tree_structure(nodes)
        self._populate_tree_widget(tree)
    
    def _build_tree_structure(self, nodes: List[Node]):
        """Build the tree structure from nodes"""
        # Create GraphTreeNode objects
        for node in nodes:
            tree_node = GraphTreeNode(node)
            self.tree_nodes[str(node.id)] = tree_node
        
        # For now, treat all nodes as root nodes since we don't have parent relationships
        # In a real implementation, you would query the Edge table to build relationships
        self.root_nodes = list(self.tree_nodes.values())
    
    def _populate_tree_widget(self, tree: Tree):
        """Populate the Textual Tree widget"""
        if not self.root_nodes:
            tree.root.add("No root nodes found")
            return
        
        # Add root nodes and their children
        for root_node in self.root_nodes:
            self._add_tree_node_recursive(tree.root, root_node)
    
    def _add_tree_node_recursive(self, parent_tree_node, graph_node: GraphTreeNode):
        """Recursively add nodes to the tree widget"""
        # Create tree node with label and data
        tree_node = parent_tree_node.add(
            graph_node.label,
            data={"node_id": graph_node.id, "graph_node": graph_node}
        )
        
        # Add CSS classes based on node type
        if graph_node.node.type == "vulnerability":
            tree_node.add_class("vulnerability")
            if graph_node.node.properties.get('severity'):
                tree_node.add_class(graph_node.node.properties['severity'].lower())
        
        # Add children
        for child in graph_node.children:
            self._add_tree_node_recursive(tree_node, child)
    
    def _add_node_to_tree(self, node: Node):
        """Add a single node to the existing tree"""
        if str(node.id) in self.tree_nodes:
            return  # Node already exists
        
        tree_node = GraphTreeNode(node)
        self.tree_nodes[str(node.id)] = tree_node
        
        # For now, add as root node since we don't have parent relationships
        # In a real implementation, you would query the Edge table to find parent
        self.root_nodes.append(tree_node)
        tree = self.query_one("#graph-tree", Tree)
        tree_node_widget = tree.root.add(
            tree_node.label,
            data={"node_id": tree_node.id, "graph_node": tree_node}
        )
        
        # Add CSS classes
        if tree_node.node.type == "vulnerability":
            tree_node_widget.add_class("vulnerability")
            if tree_node.node.properties.get('severity'):
                tree_node_widget.add_class(tree_node.node.properties['severity'].lower())
    
    def _find_tree_node_by_id(self, tree_node, node_id: str):
        """Find a tree node by its node ID"""
        if hasattr(tree_node, 'data') and tree_node.data:
            if tree_node.data.get("node_id") == node_id:
                return tree_node
        
        for child in tree_node.children:
            result = self._find_tree_node_by_id(child, node_id)
            if result:
                return result
        
        return None
    
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection"""
        if event.node.data:
            node_id = event.node.data.get("node_id")
            graph_node = event.node.data.get("graph_node")
            
            if node_id and graph_node:
                self.selected_node_id = node_id
                
                # Post node selected message
                self.post_message(NodeSelected(node_id, {
                    "node": graph_node.node,
                    "path": graph_node.get_path(),
                    "children_count": len(graph_node.children)
                }))
    
    def watch_current_scan(self, scan: Optional[ScanState]) -> None:
        """React to current scan changes"""
        self._refresh_tree()
    
    def get_selected_node(self) -> Optional[GraphTreeNode]:
        """Get the currently selected node"""
        if self.selected_node_id:
            return self.tree_nodes.get(self.selected_node_id)
        return None
    
    def expand_all(self):
        """Expand all nodes in the tree"""
        tree = self.query_one("#graph-tree", Tree)
        tree.root.expand_all()
    
    def collapse_all(self):
        """Collapse all nodes in the tree"""
        tree = self.query_one("#graph-tree", Tree)
        tree.root.collapse_all()
    
    def find_nodes_by_type(self, node_type: str) -> List[GraphTreeNode]:
        """Find all nodes of a specific type"""
        return [node for node in self.tree_nodes.values() 
                if node.node.type == node_type]
    
    def find_vulnerabilities(self) -> List[GraphTreeNode]:
        """Find all vulnerability nodes"""
        return self.find_nodes_by_type("vulnerability")
    
    def get_vulnerability_count_by_severity(self) -> Dict[str, int]:
        """Get count of vulnerabilities by severity"""
        vulnerabilities = self.find_vulnerabilities()
        severity_count = {}
        
        for vuln in vulnerabilities:
            if vuln.node.properties.get('severity'):
                severity = vuln.node.properties['severity'].lower()
                severity_count[severity] = severity_count.get(severity, 0) + 1
        
        return severity_count
    
    def refresh(self):
        """Force refresh the tree"""
        self.current_scan = app_state.get_current_scan()
        self._refresh_tree()
    
    def search_nodes(self, query: str) -> List[GraphTreeNode]:
        """Search for nodes matching the query"""
        query_lower = query.lower()
        matches = []
        
        for node in self.tree_nodes.values():
            if (query_lower in (node.node.name or "").lower() or
                query_lower in str(node.node.type).lower()):
                matches.append(node)
        
        return matches