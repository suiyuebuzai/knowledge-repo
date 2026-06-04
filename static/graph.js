// knowledge-server/static/graph.js
let network = null;
let currentNodeId = null;

function initNetwork(data) {
    const container = document.getElementById('graph-container');
    const nodes = new vis.DataSet(data.nodes);
    const edges = new vis.DataSet(data.edges);

    const options = {
        nodes: {
            shape: 'dot',
            font: { size: 12 },
        },
        edges: {
            font: { size: 9, align: 'middle' },
            arrows: { to: { enabled: true, scaleFactor: 0.5 } },
            color: { color: '#999' },
        },
        physics: {
            solver: 'forceAtlas2Based',
            forceAtlas2Based: { gravitationalConstant: -30, springLength: 100 },
            stabilization: { iterations: 100 },
        },
        interaction: { hover: true },
    };

    network = new vis.Network(container, { nodes, edges }, options);

    // 点击节点显示详情
    network.on('click', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            showDetail(nodeId, data.nodes.find(n => n.id === nodeId));
        }
    });

    // 双击节点重新以该节点为中心加载
    network.on('doubleClick', function(params) {
        if (params.nodes.length > 0) {
            loadNeighbors(params.nodes[0]);
        }
    });

    // 聚焦中心节点
    if (data.center) {
        setTimeout(() => network.focus(data.center, { scale: 1.2, animation: true }), 500);
    }
}

function showDetail(nodeId, nodeData) {
    currentNodeId = nodeId;
    const panel = document.getElementById('detail-panel');
    panel.style.display = 'block';
    document.getElementById('detail-name').textContent = nodeData.label || nodeId;
    document.getElementById('detail-info').innerHTML =
        (nodeData.title || '').replace(' | ', '<br>') +
        '<br>工号: ' + nodeId +
        '<br>体系: ' + (nodeData.group || '');
    document.getElementById('chain-result').innerHTML = '';
}

async function refreshGraph() {
    const btn = document.getElementById('refresh-btn');
    const status = document.getElementById('status-bar');
    btn.disabled = true;
    status.textContent = '正在从服务器刷新数据（约5-10秒）...';

    try {
        const resp = await fetch('/graph/api/refresh', { method: 'POST' });
        const data = await resp.json();
        if (data.error) {
            status.textContent = '刷新失败: ' + data.error;
        } else {
            status.textContent = '数据已刷新: ' + data.stats.total_persons + ' 人, ' +
                data.stats.total_departments + ' 个部门, 最大 ' + data.stats.max_depth + ' 层';
        }
    } catch (e) {
        status.textContent = '刷新失败: ' + e.message;
    }
    btn.disabled = false;
}

async function doSearch() {
    const q = document.getElementById('search-input').value.trim();
    if (!q) return;

    const resp = await fetch('/graph/api/search?q=' + encodeURIComponent(q));
    const data = await resp.json();

    if (data.error) {
        document.getElementById('status-bar').textContent = data.error;
        return;
    }

    const resultsEl = document.getElementById('search-results');
    if (data.results.length === 0) {
        resultsEl.style.display = 'block';
        resultsEl.innerHTML = '<span style="color:#c5221f;">未找到匹配人员</span>';
        return;
    }

    if (data.results.length === 1) {
        resultsEl.style.display = 'none';
        loadNeighbors(data.results[0].empno);
        return;
    }

    // 多个结果，显示选择列表
    resultsEl.style.display = 'block';
    resultsEl.innerHTML = data.results.map(r =>
        '<a href="#" onclick="loadNeighbors(\'' + r.empno + '\');return false;">' +
        r.empname + '(' + r.empno + ') - ' + r.deptname + '</a>'
    ).join('');
}

async function loadNeighbors(empno) {
    document.getElementById('search-results').style.display = 'none';
    const resp = await fetch('/graph/api/neighbors?id=' + empno + '&depth=2');
    const data = await resp.json();
    if (data.error) {
        document.getElementById('status-bar').textContent = data.error;
        return;
    }
    initNetwork(data);
}

async function showChain() {
    if (!currentNodeId) return;
    const resp = await fetch('/graph/api/chain?id=' + currentNodeId + '&direction=up');
    const data = await resp.json();
    if (data.chain) {
        document.getElementById('chain-result').innerHTML =
            '<strong>上级链:</strong><br>' +
            data.chain.map(p => p.empname + '(' + p.jobname + ')').join(' -> ');
    }
}

function promptPath() {
    if (!currentNodeId) return;
    const target = prompt('输入目标人员工号:');
    if (target) findPath(currentNodeId, target);
}

async function findPath(source, target) {
    const resp = await fetch('/graph/api/path?source=' + source + '&target=' + target);
    const data = await resp.json();
    if (data.path && data.path.length > 0) {
        document.getElementById('chain-result').innerHTML =
            '<strong>路径:</strong><br>' +
            data.path.map(p => p.empname).join(' -> ') +
            (data.common_superior ? '<br><strong>共同上级:</strong> ' + data.common_superior.empname : '');
    } else {
        document.getElementById('chain-result').innerHTML = '<span style="color:#c5221f;">未找到路径</span>';
    }
}

// 回车键触发搜索
document.getElementById('search-input').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') doSearch();
});
