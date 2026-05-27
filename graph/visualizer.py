# graph/visualizer.py
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec


def build_graph(objects: dict, refs: dict) -> nx.DiGraph:
    G = nx.DiGraph()
    for obj_id, obj in objects.items():
        G.add_node(obj_id,
                   site=obj.site_id,
                   deleted=obj.deleted,
                   total_rc=obj.total_rc,
                   local_rc=obj.local_rc)
    for ref_id, ref in refs.items():
        if ref.from_obj in G.nodes and ref.to_obj in G.nodes:
            G.add_edge(ref.from_obj, ref.to_obj,
                       alive=ref.alive,
                       ref_id=ref_id)
    return G


def draw_graph(objects: dict, refs: dict,
               title: str = "DGC Object Graph",
               save_path: str = None):
    G = build_graph(objects, refs)

    fig, ax = plt.subplots(figsize=(14, 9))
    ax.set_title(title, fontsize=14, fontweight='bold', pad=15)

    # Layout — tách Site A bên trái, Site B bên phải
    pos = {}
    a_nodes = [n for n, d in G.nodes(data=True) if d['site'] == 'A']
    b_nodes = [n for n, d in G.nodes(data=True) if d['site'] == 'B']

    for i, n in enumerate(sorted(a_nodes)):
        pos[n] = (-2, i - len(a_nodes)/2)
    for i, n in enumerate(sorted(b_nodes)):
        pos[n] = (2, i - len(b_nodes)/2)

    # Màu nodes
    node_colors = []
    node_sizes  = []
    node_labels = {}
    for node, data in G.nodes(data=True):
        if data['deleted']:
            color = '#FF6B6B'
            size  = 700
        elif data['site'] == 'A':
            color = '#4ECDC4'
            size  = 1200
        elif data['total_rc'] == 0:
            color = '#FFE66D'
            size  = 900
        else:
            color = '#95E1D3'
            size  = 1000
        node_colors.append(color)
        node_sizes.append(size)
        node_labels[node] = f"{node}\nRC={data['total_rc']}"

    # Edges
    alive_edges = [(u,v) for u,v,d in G.edges(data=True) if d.get('alive', True)]
    dead_edges  = [(u,v) for u,v,d in G.edges(data=True) if not d.get('alive', True)]

    nx.draw_networkx_nodes(G, pos, node_color=node_colors,
                           node_size=node_sizes, ax=ax, alpha=0.92)
    nx.draw_networkx_labels(G, pos, labels=node_labels,
                            font_size=8, ax=ax, font_weight='bold')
    nx.draw_networkx_edges(G, pos, edgelist=alive_edges,
                           edge_color='#2196F3', arrows=True,
                           arrowsize=25, width=2.5, ax=ax,
                           connectionstyle='arc3,rad=0.15')
    nx.draw_networkx_edges(G, pos, edgelist=dead_edges,
                           edge_color='#FF5252', arrows=True,
                           arrowsize=18, width=1.5, ax=ax,
                           style='dashed', connectionstyle='arc3,rad=0.15')

    # Nhãn site
    ax.text(-2, len(a_nodes)/2 + 0.8, 'SITE A', fontsize=12,
            fontweight='bold', color='#2196F3', ha='center')
    ax.text( 2, len(b_nodes)/2 + 0.8, 'SITE B', fontsize=12,
            fontweight='bold', color='#1D9E75', ha='center')

    # Legend
    legend = [
        mpatches.Patch(color='#4ECDC4', label='Site A object'),
        mpatches.Patch(color='#95E1D3', label='Site B — alive'),
        mpatches.Patch(color='#FFE66D', label='GC candidate (RC=0)'),
        mpatches.Patch(color='#FF6B6B', label='Deleted'),
        mpatches.Patch(color='#2196F3', label='Active reference'),
        mpatches.Patch(color='#FF5252', label='Expired / dead ref'),
    ]
    ax.legend(handles=legend, loc='lower center',
              ncol=3, fontsize=9, framealpha=0.9)
    ax.axis('off')
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"[Graph] Saved → {save_path}")
    plt.show()
    plt.close()


def draw_experiment_chart(results: list, x_key: str,
                           x_label: str, title: str,
                           save_path: str = None):
    """Vẽ biểu đồ kết quả thí nghiệm — dùng trong báo cáo."""
    x      = [r[x_key] for r in results]
    leaked = [r['leaked'] for r in results]
    false_ = [r['false_deletes'] for r in results]
    collec = [r['correctly_collected'] for r in results]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(title, fontsize=13, fontweight='bold')

    # Biểu đồ trái: leaked và false delete
    ax1.plot(x, leaked, 'r-o', label='Leaked', linewidth=2, markersize=8)
    ax1.plot(x, false_, 'b-s', label='False delete', linewidth=2, markersize=8)
    ax1.set_xlabel(x_label, fontsize=11)
    ax1.set_ylabel('Object count', fontsize=11)
    ax1.set_title('Errors', fontsize=11)
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(-0.5, max(max(leaked), max(false_), 1) + 1)

    # Biểu đồ phải: correctly collected
    ax2.bar([str(v) for v in x], collec,
            color='#95E1D3', edgecolor='#1D9E75', linewidth=1.5)
    ax2.set_xlabel(x_label, fontsize=11)
    ax2.set_ylabel('Objects collected', fontsize=11)
    ax2.set_title('Correctly Collected', fontsize=11)
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"[Chart] Saved → {save_path}")
    plt.show()
    plt.close()