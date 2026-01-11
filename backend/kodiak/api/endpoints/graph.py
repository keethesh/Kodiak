from typing import List, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from kodiak.database import get_session
from kodiak.database.models import Node, Edge, Finding

router = APIRouter()

@router.get("/{project_id}", response_model=Dict[str, Any])
async def get_project_knowledge_graph(project_id: UUID, session: AsyncSession = Depends(get_session)):
    """
    Returns the full Knowledge Graph (Nodes + Edges) for visualization.
    Format optimized for react-force-graph: { "nodes": [], "links": [] }
    """
    
    # 1. Fetch Nodes
    stmt_nodes = select(Node).where(Node.project_id == project_id)
    nodes = (await session.execute(stmt_nodes)).scalars().all()
    
    # 2. Fetch Edges
    stmt_edges = select(Edge).where(Edge.source_id.in_([n.id for n in nodes])) # Optimization needed for large graphs
    # Better: join or select all edges for project (if Edge had project_id... it connects nodes, so implied)
    # MVP: Fetch all edges where source or target is in nodes list
    # Actually, simplest MVP: Edge should probably have project_id denormalized for speed?
    # For now, let's just fetch all edges that connect two known nodes.
    
    # Let's just create Edge with project_id in future. For now, we query Edge table.
    stmt_all_edges = select(Edge) 
    all_edges = (await session.execute(stmt_all_edges)).scalars().all()
    
    # Filter edges in python for MVP (BAD for scale, good for prototype)
    valid_node_ids = {n.id for n in nodes}
    project_edges = [e for e in all_edges if e.source_id in valid_node_ids and e.target_id in valid_node_ids]

    # 3. Format
    graph_data = {
        "nodes": [],
        "links": []
    }
    
    for n in nodes:
        # Check findings max severity for color
        color = "green"
        # We need to fetch findings for each node? Batch fetch preferred.
        # MVP: Client fetches findings on click. Server sends "has_issues" flag?
        
        graph_data["nodes"].append({
            "id": str(n.id),
            "label": n.name,
            "type": n.type,
            "group": n.type, # for color coding
            "val": 10 if n.type == "domain" else 5, # size
            "metadata": n.properties
        })
        
    for e in project_edges:
        graph_data["links"].append({
            "source": str(e.source_id),
            "target": str(e.target_id),
            "label": e.relation
        })
        
    return graph_data
