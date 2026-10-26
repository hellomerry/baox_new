// 报销稽核系统前端 JS
// 三客户端共用入口

const App = {
    clientType: window.location.pathname.includes('finance') ? 'finance' :
                window.location.pathname.includes('auditor') ? 'auditor' : 'reimburser',
    currentUser: null,
    currentView: 'dashboard',

    // ============= 工具 =============
    api: {
        async request(method, url, data) {
            const opts = {
                method,
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
            };
            if (data && method !== 'GET') opts.body = JSON.stringify(data);
            const r = await fetch(url, opts);
            return await r.json();
        },
        get(url) { return this.request('GET', url); },
        post(url, data) { return this.request('POST', url, data); },
    },

    formatDate(d) {
        if (!d) return '';
        return d.split('T')[0];
    },

    formatMoney(n) {
        if (n == null) return '0.00';
        return Number(n).toFixed(2);
    },

    escape(s) {
        if (s == null) return '';
        return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
    },

    // ============= 视图 =============
    showLogin(msg = '') {
        document.getElementById('login-view').style.display = 'block';
        document.getElementById('main-view').style.display = 'none';
        document.getElementById('login-message').textContent = msg;
        document.getElementById('login-message').className = 'form-message' + (msg ? ' error' : '');
        document.getElementById('login-username').focus();
    },

    showMain() {
        document.getElementById('login-view').style.display = 'none';
        document.getElementById('main-view').style.display = 'block';
        document.getElementById('current-user').textContent =
            `${this.currentUser.real_name}（${this.currentUser.username}）`;
    },

    // ============= 登录 =============
    async checkSession() {
        const r = await this.api.get('/api/auth/me');
        if (r.code === 0) {
            this.currentUser = r.data;
            this.showMain();
            this.buildMenu();
            this.navigate('dashboard');
        } else {
            this.showLogin();
        }
    },

    async handleLogin(e) {
        e.preventDefault();
        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;
        const r = await this.api.post('/api/auth/login', { username, password });
        if (r.code === 0) {
            this.currentUser = r.data;
            this.showMain();
            this.buildMenu();
            this.navigate('dashboard');
            this._updateUnreadBadge();
            if (r.data.must_change_password) {
                alert('首次登录必须修改密码');
                this.navigate('change-password');
            }
        } else {
            this.showLogin(r.message);
        }
        return false;
    },

    async logout() {
        await this.api.get('/api/auth/logout');
        window.location.href = '/';
    },

    // ============= 菜单 =============
    buildMenu() {
        const menus = {
            finance: [
                { id: 'dashboard', label: '工作台', icon: '🏠' },
                { id: 'bills', label: '报销单管理', icon: '📋' },
                { id: 'audit-pending', label: '待审单据', icon: '⏰' },
                { id: 'final-audit', label: '财务终审', icon: '💰' },
                { id: 'pending-dual-sign', label: '待双签', icon: '🤝' },
                { id: 'override-history', label: '强制修改历史', icon: '⚡' },
                { id: 'projects', label: '项目台账', icon: '📂' },
                { id: 'users', label: '人员账号', icon: '👥' },
                { id: 'standards', label: '报销标准', icon: '📊' },
                { id: 'attendance', label: '考勤查询', icon: '📅' },
                { id: 'reports', label: '统计报表', icon: '📈' },
                { id: 'data-import', label: '数据导入向导', icon: '📥' },
                { id: 'packages', label: '数据包交换', icon: '📦' },
                { id: 'sync', label: '中心节点同步', icon: '🔄' },
                { id: 'audit-logs', label: '审计日志', icon: '📜' },
                { id: 'research-audit', label: '终审独立审计', icon: '🔍' },
                { id: 'upgrade', label: '应用升级', icon: '🚀' },
                { id: 'data-dict', label: '数据字典', icon: '📖' },
                { id: 'data-export', label: '数据导出', icon: '📤' },
                { id: 'dashboard-screen', label: '可视化大屏', icon: '📊' },
                { id: 'ocr', label: '票据识别', icon: '📷' },
                { id: 'transfer-ocr', label: '调令识别', icon: '📑' },
                { id: 'notifications', label: '通知中心', icon: '🔔' },
                { id: 'change-password', label: '修改密码', icon: '🔑' },
            ],
            auditor: [
                { id: 'dashboard', label: '工作台', icon: '🏠' },
                { id: 'my-bills', label: '待审单据', icon: '⏰' },
                { id: 'all-bills', label: '我的报销人单据', icon: '📋' },
                { id: 'reimbursers', label: '我的报销人', icon: '👤' },
                { id: 'projects', label: '项目台账', icon: '📂' },
                { id: 'agents', label: '代理关系', icon: '🤝' },
                { id: 'agent-fill', label: '代填报销', icon: '✍️' },
                { id: 'attendance-pending', label: '考勤审批', icon: '✅' },
                { id: 'attendance', label: '考勤', icon: '📅' },
                { id: 'audit-logs', label: '操作日志', icon: '📜' },
                { id: 'research-audit', label: '终审独立审计', icon: '🔍' },
                { id: 'transfer-ocr', label: '调令识别', icon: '📑' },
                { id: 'notifications', label: '通知中心', icon: '🔔' },
                { id: 'change-password', label: '修改密码', icon: '🔑' },
            ],
            reimburser: [
                { id: 'dashboard', label: '工作台', icon: '🏠' },
                { id: 'my-bills', label: '我的报销单', icon: '📋' },
                { id: 'new-bill', label: '新建报销', icon: '➕' },
                { id: 'attendance', label: '考勤录入', icon: '📅' },
                { id: 'my-info', label: '我的资料', icon: '👤' },
                { id: 'notifications', label: '通知中心', icon: '🔔' },
                { id: 'change-password', label: '修改密码', icon: '🔑' },
            ],
        };

        const menu = menus[this.currentUser.role] || [];
        const html = menu.map(m =>
            `<a class="menu-item" data-view="${m.id}"><span class="icon">${m.icon}</span><span class="label">${m.label}</span></a>`
        ).join('');
        document.getElementById('sidebar-menu').innerHTML = html;
        document.querySelectorAll('.menu-item').forEach(el => {
            el.addEventListener('click', () => this.navigate(el.dataset.view));
        });
    },

    // ============= 路由 =============
    navigate(view) {
        this.currentView = view;
        document.querySelectorAll('.menu-item').forEach(el => el.classList.remove('active'));
        const item = document.querySelector(`.menu-item[data-view="${view}"]`);
        if (item) item.classList.add('active');
        this.renderView(view);
    },

    renderView(view) {
        // view id → method name 映射（少数 view 用非标准命名）
        const viewMap = {
            'dashboard': 'dashboard_main',
            'dashboard-screen': 'dashboard_screen',
        };
        const methodName = viewMap[view] || view.replace(/-/g, '_');
        const title = {
            'dashboard': '工作台',
            'dashboard-screen': '可视化大屏',
            'bills': '报销单管理',
            'audit-pending': '待审单据',
            'projects': '项目台账',
            'users': '人员账号',
            'standards': '报销标准',
            'attendance': '考勤',
            'reports': '统计报表',
            'packages': '数据包交换',
            'sync': '中心节点同步',
            'audit-logs': '审计日志',
            'change-password': '修改密码',
            'my-bills': '我的报销单',
            'all-bills': '我的报销人单据',
            'reimbursers': '我的报销人',
            'agent-fill': '代填报销',
            'new-bill': '新建报销',
            'my-info': '我的资料',
            'transfer-ocr': '人员调令识别',
        };
        document.getElementById('view-title').textContent = title[view] || view;
        const c = document.getElementById('view-content');
        c.innerHTML = '<p class="placeholder">加载中...</p>';
        this['_view_' + (view.replace(/-/g, '_'))] ? this['_view_' + view.replace(/-/g, '_')](c) : c.innerHTML = '<p class="placeholder">未实现</p>';
    },

    // ============= 视图：工作台 =============
    async _view_dashboard_main(c) {
        const r = await this.api.get('/api/bills/list');
        const bills = r.data || [];
        const stats = {
            total: bills.length,
            draft: bills.filter(b => b.status === 'draft').length,
            pending: bills.filter(b => ['submitted_auditor', 'auditor_ok', 'submitted_finance'].includes(b.status)).length,
            archived: bills.filter(b => b.status === 'archived').length,
        };

        c.innerHTML = `
            <div class="stat-grid">
                <div class="stat-card"><div class="stat-num">${stats.total}</div><div class="stat-label">全部单据</div></div>
                <div class="stat-card"><div class="stat-num">${stats.draft}</div><div class="stat-label">草稿</div></div>
                <div class="stat-card"><div class="stat-num">${stats.pending}</div><div class="stat-label">流转中</div></div>
                <div class="stat-card"><div class="stat-num">${stats.archived}</div><div class="stat-label">已归档</div></div>
            </div>
            <div class="card">
                <h3>欢迎回来，${this.escape(this.currentUser.real_name)}</h3>
                <p>当前角色：<strong>${this.currentUser.role}</strong> ｜ 客户端类型：<strong>${this.currentUser.role}</strong>版</p>
                <p>请从左侧菜单选择功能，或在下方查看最近单据：</p>
            </div>
            <div class="card">
                <h3>最近单据</h3>
                ${this._renderBillTable(bills.slice(0, 5))}
            </div>
        `;
    },

    // ============= 视图：报销单列表 =============
    async _view_bills(c) {
        const r = await this.api.get('/api/bills/list');
        const bills = r.data || [];
        c.innerHTML = `
            <div class="toolbar">
                <input type="text" id="bill-search" placeholder="搜索单号" class="search-input">
                <select id="bill-status-filter">
                    <option value="">全部状态</option>
                    <option value="draft">草稿</option>
                    <option value="submitted_auditor">待初审</option>
                    <option value="rejected_auditor">稽核驳回</option>
                    <option value="auditor_ok">已初审</option>
                    <option value="submitted_finance">待终审</option>
                    <option value="approved">已批准</option>
                    <option value="archived">已归档</option>
                </select>
                <button class="btn btn-primary" onclick="App.filterBills()">查询</button>
            </div>
            <div class="card">
                ${this._renderBillTable(bills)}
            </div>
        `;
        document.getElementById('bill-search').addEventListener('keyup', (e) => {
            if (e.key === 'Enter') this.filterBills();
        });
    },

    async filterBills() {
        const kw = document.getElementById('bill-search').value;
        const status = document.getElementById('bill-status-filter').value;
        const params = new URLSearchParams();
        if (status) params.set('status', status);
        const r = await this.api.get('/api/bills/list?' + params);
        let bills = r.data || [];
        if (kw) bills = bills.filter(b => b.bill_no.includes(kw));
        document.querySelector('.card').innerHTML = this._renderBillTable(bills);
    },

    _renderBillTable(bills) {
        if (!bills.length) return '<p class="placeholder">暂无单据</p>';
        return `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>单号</th>
                        <th>报销人</th>
                        <th>项目</th>
                        <th>日期</th>
                        <th>金额</th>
                        <th>状态</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${bills.map(b => `
                        <tr>
                            <td>${this.escape(b.bill_no)}</td>
                            <td>${this.escape(b.user_name || '-')}</td>
                            <td>${this.escape(b.project_name || '-')}</td>
                            <td>${this.formatDate(b.travel_start_date)} ~ ${this.formatDate(b.travel_end_date)}</td>
                            <td>¥${this.formatMoney(b.total_amount)}</td>
                            <td><span class="status-tag status-${b.status}">${this._statusText(b.status)}</span></td>
                            <td><button class="btn btn-sm" onclick="App.viewBill(${b.id})">查看</button></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    },

    _statusText(s) {
        return {
            'draft': '草稿',
            'submitted_auditor': '待初审',
            'rejected_auditor': '稽核驳回',
            'auditor_ok': '已初审',
            'submitted_finance': '待终审',
            'rejected_finance': '财务驳回',
            'approved': '已批准',
            'archived': '已归档',
        }[s] || s;
    },

    // ============= 视图：单据详情 =============
    async viewBill(billId) {
        const r = await this.api.get('/api/bills/' + billId);
        if (r.code !== 0) {
            alert(r.message);
            return;
        }
        const b = r.data;
        const role = this.currentUser.role;

        let actionHtml = '';
        if (role === 'auditor' && b.status === 'submitted_auditor' && b.auditor_id === this.currentUser.user_id) {
            actionHtml = `
                <div id="precheck-box"></div>
                <textarea id="audit-comment" placeholder="审核意见" class="form-control"></textarea>
                <div class="action-buttons">
                    <button class="btn btn-primary" onclick="App.doAudit(${billId}, 'approve')">通过</button>
                    <button class="btn btn-danger" onclick="App.doAudit(${billId}, 'reject')">驳回</button>
                </div>
            `;
        } else if (role === 'finance' && (b.status === 'auditor_ok' || b.status === 'submitted_finance')) {
            actionHtml = `
                <div id="precheck-box"></div>
                <textarea id="audit-comment" placeholder="终审意见" class="form-control"></textarea>
                <div class="action-buttons">
                    <button class="btn btn-primary" onclick="App.doFinanceAudit(${billId}, 'approve')">终审通过</button>
                    <button class="btn btn-danger" onclick="App.doFinanceAudit(${billId}, 'reject')">驳回</button>
                </div>
            `;
        } else if (role === 'reimburser' && b.status === 'draft' && b.user_id === this.currentUser.user_id) {
            actionHtml = `
                <div class="action-buttons">
                    <button class="btn btn-primary" onclick="App.doSubmit(${billId})">提交</button>
                    <button class="btn btn-danger" onclick="App.doDelete(${billId})">删除</button>
                </div>
            `;
        }

        // 所有角色都能：导出 PDF/Word / 上传附件 / 查看附件
        let financeActions = '';
        if (role === 'finance' && (b.status === 'archived' || b.status === 'approved') && !b.red_rushed) {
            financeActions = `<button class="btn btn-danger" onclick="App.doRedRush(${billId})">🔁 冲红</button>`;
        }
        const redRushedTag = b.red_rushed ? '<span class="status-tag" style="background:#fff1f0;color:#f5222d;">已冲红</span>' : '';

        // D3 终审 + 双签状态显示
        const dualSignInfo = (b.status === 'pending_dual_sign' || b.finance_dual_signed || b.finance_dual_signer_id) ? `
            <div class="audit-chain-status ${b.status === 'pending_dual_sign' ? 'error' : 'ok'}">
                <strong>🔍 双签状态</strong>：${
                    b.status === 'pending_dual_sign'
                        ? `<span style="color: #e74c3c;">⏳ 等待第二签人批准</span>（指定 ID #${b.finance_dual_signer_id}）`
                        : b.finance_dual_signed
                            ? `✓ 双签通过（第二签人 #${b.finance_dual_signer_id}，签字时间：${b.finance_dual_sign_at || '-'}）`
                            : b.finance_dual_signer_id
                                ? `双签被拒（原因：${this.escape(b.finance_dual_comment || '-')}）`
                                : ''
                }
            </div>
        ` : '';

        // D3 override 按钮（仅财务可操作）
        const overrideBtn = (this.currentUser.role === 'finance' && !b.red_rushed) ? `
            <button class="btn" style="background: #e67e22; color: white;" onclick="App._doOverride(${billId})">
                ⚡ 强制修改
            </button>
        ` : '';

        const alwaysHtml = `
            <div class="action-buttons">
                <a class="btn btn-primary" href="/api/bills/${billId}/pdf" target="_blank">📄 导出 PDF</a>
                <a class="btn btn-primary" href="/api/bills/${billId}/docx" target="_blank">📝 导出 Word</a>
                <button class="btn" onclick="App.showUploadDialog(${billId})">📎 上传附件</button>
                <button class="btn" onclick="App.showAttachments(${billId})">📂 查看附件</button>
                <button class="btn" onclick="App._viewDecisionChain(${billId})">🔍 查看决策链</button>
                ${overrideBtn}
                ${financeActions}
                ${redRushedTag}
            </div>
        `;

        document.getElementById('view-content').innerHTML = `
            <div class="card">
                <h3>${this.escape(b.bill_no)} <span class="status-tag status-${b.status}">${this._statusText(b.status)}</span></h3>
                ${dualSignInfo}
                <div class="info-grid">
                    <div><label>类型</label><span>${b.bill_type === 'project_total' ? '项目总账' : '个人报销'}</span></div>
                    <div><label>报销人</label><span>${this.escape(b.user_name || '-')}</span></div>
                    <div><label>项目</label><span>${this.escape(b.project_name || '-')}</span></div>
                    <div><label>出发日期</label><span>${this.formatDate(b.travel_start_date)}</span></div>
                    <div><label>返回日期</label><span>${this.formatDate(b.travel_end_date)}</span></div>
                    <div><label>目的地</label><span>${this.escape(b.destination || '-')}</span></div>
                </div>
                <h4>金额明细</h4>
                <table class="data-table">
                    <tr><th>交通</th><td>¥${this.formatMoney(b.transport_fee)}</td></tr>
                    <tr><th>住宿</th><td>¥${this.formatMoney(b.accommodation_fee)}</td></tr>
                    <tr><th>补助</th><td>¥${this.formatMoney(b.subsidy_fee)}</td></tr>
                    <tr><th>其他</th><td>¥${this.formatMoney(b.other_fee)}</td></tr>
                    <tr><th>合计</th><td><strong>¥${this.formatMoney(b.total_amount)}</strong></td></tr>
                    <tr><th>大写</th><td>${this.escape(b.capital_amount)}</td></tr>
                </table>
                ${b.auditor_name ? `<h4>稽核员意见</h4><p>${this.escape(b.auditor_comment || '-')} - ${this.escape(b.auditor_name)} ${b.auditor_audit_at || ''}</p>` : ''}
                ${b.finance_auditor_id ? `<h4>财务意见</h4><p>${this.escape(b.finance_comment || '-')}</p>` : ''}
                ${actionHtml}
                ${alwaysHtml}
                <button class="btn" onclick="App.goBack()">返回</button>
            </div>
        `;

        // 审核界面存在时异步加载稽核预检预警（考勤联动 + 调令校验）
        if (document.getElementById('precheck-box')) {
            this._loadPrecheck(billId);
        }
    },

    // 稽核预检预警加载（考勤联动 + 调令校验）
    async _loadPrecheck(billId) {
        const box = document.getElementById('precheck-box');
        if (!box) return;
        try {
            const r = await this.api.get(`/api/bills/${billId}/precheck`);
            if (r.code !== 0) return;
            const warns = (r.data || []).filter(p => p.status === 'warning');
            if (!warns.length) return;
            const labels = { attendance: '📅 考勤联动', transfer: '📄 调令校验' };
            box.innerHTML = `
                <div class="audit-chain-status error" style="margin-bottom: 8px;">
                    <strong>⚠️ 稽核预检预警</strong>
                    ${warns.map(w => `
                        <div style="margin-top: 4px;">
                            <strong>${labels[w.rule] || w.rule}</strong>：${this.escape(w.message)}
                        </div>
                    `).join('')}
                    <div style="color: #999; font-size: 12px; margin-top: 4px;">预警不阻断审批，请核实后决策；通过后预警将写入审计日志</div>
                </div>
            `;
        } catch (e) { /* 预检失败不阻塞审核界面 */ }
    },

    // D3 override 强制修改
    async _doOverride(billId) {
        const targetStatus = prompt(
            '强制修改目标状态（输入目标状态）：\n' +
            'draft / submitted / submitted_auditor / auditor_ok /\n' +
            'submitted_finance / approved / rejected_auditor /\n' +
            'rejected_finance / archived'
        );
        if (!targetStatus) return;
        const reason = prompt('原因（≥10 字符，用于审计追溯）：');
        if (!reason || reason.length < 10) {
            alert('原因至少 10 个字符');
            return;
        }
        const r = await this.api.post(`/api/bills/${billId}/override`, {
            target_status: targetStatus,
            reason: reason,
        });
        if (r.code !== 0) {
            alert('强制修改失败：' + r.message);
            return;
        }
        alert('✓ 已强制修改，记录已写入终审独立审计');
        this.viewBill(billId);
    },

    // ============= 附件：上传对话框 =============
    showUploadDialog(billId) {
        document.getElementById('view-content').innerHTML = `
            <div class="card">
                <h3>上传附件 - 单据 #${billId}</h3>
                <p style="color: #999; font-size: 13px; margin-bottom: 16px;">
                    支持格式：png / jpg / pdf / gif / bmp，最大 50MB
                </p>
                <form id="upload-form" enctype="multipart/form-data">
                    <div class="form-group">
                        <label>选择文件</label>
                        <input type="file" id="att-file" required>
                    </div>
                    <div class="form-message" id="up-msg"></div>
                    <div class="action-buttons">
                        <button type="button" class="btn btn-primary" onclick="App.doUpload(${billId})">上传</button>
                        <button type="button" class="btn" onclick="App.viewBill(${billId})">取消</button>
                    </div>
                </form>
            </div>
        `;
    },

    async doUpload(billId) {
        const fileInput = document.getElementById('att-file');
        if (!fileInput.files.length) {
            document.getElementById('up-msg').textContent = '请选择文件';
            document.getElementById('up-msg').className = 'form-message error';
            return;
        }

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);

        const r = await fetch(`/api/attachments/upload/${billId}`, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
        });
        const result = await r.json();
        document.getElementById('up-msg').textContent = result.message;
        document.getElementById('up-msg').className = 'form-message' + (result.code === 0 ? ' success' : ' error');
        if (result.code === 0) {
            setTimeout(() => this.showAttachments(billId), 1000);
        }
    },

    // ============= 附件：查看列表 =============
    async showAttachments(billId) {
        const r = await this.api.get(`/api/attachments/list/${billId}`);
        const items = r.data || [];

        document.getElementById('view-content').innerHTML = `
            <div class="card">
                <h3>附件列表 - 单据 #${billId}</h3>
                ${items.length ? `
                    <table class="data-table">
                        <thead><tr><th>文件名</th><th>大小</th><th>SHA256</th><th>上传时间</th><th>操作</th></tr></thead>
                        <tbody>
                            ${items.map(a => `
                                <tr>
                                    <td>${this.escape(a.file_name)}</td>
                                    <td>${(a.file_size / 1024).toFixed(1)} KB</td>
                                    <td><code style="font-size: 11px;">${a.file_hash.substring(0, 16)}...</code></td>
                                    <td>${this.formatDate(a.uploaded_at)}</td>
                                    <td>
                                        <a class="btn btn-sm" href="/api/attachments/${a.id}/download" target="_blank">下载</a>
                                        <button class="btn btn-sm" onclick="App.verifyAtt(${a.id}, ${billId})">校验</button>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                ` : '<p class="placeholder">暂无附件</p>'}
                <div class="action-buttons">
                    <button class="btn btn-primary" onclick="App.showUploadDialog(${billId})">+ 上传新附件</button>
                    <button class="btn" onclick="App.viewBill(${billId})">返回单据</button>
                </div>
            </div>
        `;
    },

    async verifyAtt(attId, billId) {
        const r = await this.api.get(`/api/attachments/${attId}/verify`);
        alert(r.data.valid ? '✅ ' + r.message : '❌ ' + r.message);
    },

    goBack() {
        this.renderView(this.currentView);
    },

    async doSubmit(billId) {
        if (!confirm('确认提交？提交后将进入稽核流程。')) return;
        const r = await this.api.post(`/api/bills/${billId}/submit`);
        alert(r.message);
        if (r.code === 0) this.viewBill(billId);
    },

    async doDelete(billId) {
        if (!confirm('确认删除？仅 draft 状态可删除。')) return;
        const r = await this.api.post(`/api/bills/${billId}/delete`);
        alert(r.message);
        if (r.code === 0) this.renderView(this.currentView);
    },

    async doAudit(billId, decision) {
        const comment = document.getElementById('audit-comment').value;
        const r = await this.api.post(`/api/bills/${billId}/auditor-audit`, { decision, comment });
        alert(r.message);
        if (r.code === 0) this.viewBill(billId);
    },

    async doFinanceAudit(billId, decision) {
        const comment = document.getElementById('audit-comment').value;
        const r = await this.api.post(`/api/bills/${billId}/finance-audit`, { decision, comment });
        alert(r.message);
        if (r.code === 0) this.viewBill(billId);
    },

    async doRedRush(billId) {
        const reason = prompt('请输入冲红原因（必填）：');
        if (!reason || !reason.trim()) {
            alert('冲红原因不能为空');
            return;
        }
        if (!confirm('确认冲红？将生成一张金额为负的反向单据，需走终审流程。')) return;
        const r = await this.api.post(`/api/bills/${billId}/red-rush`, { reason: reason.trim() });
        alert(r.message);
        if (r.code === 0) this.viewBill(billId);
    },

    // ============= 视图：自然人查询 =============
    async _view_same_natural(c, userId) {
        const r = await this.api.get(`/api/users/${userId}/same-natural`);
        const same = r.data || [];
        c.innerHTML = `
            <div class="card">
                <h3>同一自然人的其他账号</h3>
                <p style="color: #999; font-size: 13px; margin-bottom: 16px;">
                    用于检测跨账号逃避自审回避（C4 决策）
                </p>
                ${same.length ? `
                    <table class="data-table">
                        <thead><tr><th>账号</th><th>姓名</th><th>角色</th><th>人员类型</th></tr></thead>
                        <tbody>
                            ${same.map(u => `
                                <tr>
                                    <td>${this.escape(u.username)}</td>
                                    <td>${this.escape(u.real_name)}</td>
                                    <td>${u.role}</td>
                                    <td>${this.escape(u.staff_type || '-')}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                ` : '<p class="placeholder">该人员没有跨账号情况</p>'}
                <div class="action-buttons">
                    <button class="btn" onclick="App.navigate('users')">返回人员列表</button>
                </div>
            </div>
        `;
    },

    // ============= 视图：我的报销单 =============
    async _view_my_bills(c) {
        const r = await this.api.get('/api/bills/list');
        const bills = (r.data || []).filter(b => b.user_id === this.currentUser.user_id);
        c.innerHTML = `<div class="card">${this._renderBillTable(bills)}</div>`;
    },

    // ============= 视图：我的报销人单据（稽核员） =============
    async _view_all_bills(c) {
        const r = await this.api.get('/api/bills/list');
        c.innerHTML = `<div class="card">${this._renderBillTable(r.data || [])}</div>`;
    },

    // ============= 视图：待审单据 =============
    async _view_audit_pending(c) {
        const r = await this.api.get('/api/bills/list?status=submitted_auditor');
        c.innerHTML = `<div class="card"><h3>待审单据</h3>${this._renderBillTable(r.data || [])}</div>`;
    },

    // ============= 视图：财务终审工作台（D3 决策） =============
    async _view_final_audit(c) {
        const r = await this.api.get('/api/bills/list?status=submitted_finance');
        const bills = r.data || [];
        const lowAmount = bills.filter(b => parseFloat(b.total_amount || 0) < 100000);
        const highAmount = bills.filter(b => parseFloat(b.total_amount || 0) >= 100000);

        c.innerHTML = `
            <div class="card">
                <h3>财务终审工作台（D3 决策）</h3>
                <p class="hint">
                    终审是单据最终决定环节。小额（&lt; 10 万）由主财务直接通过；大额（≥ 10 万）需双签：主财务 approve 后变为
                    <code>pending_dual_sign</code>，等待指定第二签人登录批准。
                </p>
                <div class="stat-grid">
                    <div class="stat-card stat-card-primary">
                        <div class="stat-num">${bills.length}</div>
                        <div class="stat-label">待终审</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-num">${lowAmount.length}</div>
                        <div class="stat-label">小额（单签）</div>
                    </div>
                    <div class="stat-card" style="background: linear-gradient(135deg, #e67e22 0%, #d35400 100%); color: white;">
                        <div class="stat-num">${highAmount.length}</div>
                        <div class="stat-label" style="color: rgba(255,255,255,0.9);">大额（双签）</div>
                    </div>
                </div>
            </div>
            <div class="card">
                <h3>待终审单据（${bills.length}）</h3>
                ${bills.length ? bills.map(b => this._renderFinalAuditCard(b)).join('') : '<p class="placeholder">无待终审单据</p>'}
            </div>
        `;

        // 绑定操作按钮
        c.querySelectorAll('[data-action="final-approve"]').forEach(btn => {
            btn.onclick = () => this._doFinalAudit(parseInt(btn.dataset.billId), 'approve');
        });
        c.querySelectorAll('[data-action="final-reject"]').forEach(btn => {
            btn.onclick = () => this._doFinalAudit(parseInt(btn.dataset.billId), 'reject');
        });
    },

    _renderFinalAuditCard(b) {
        const isHigh = parseFloat(b.total_amount || 0) >= 100000;
        return `
            <div class="bill-card" style="border-left: 4px solid ${isHigh ? '#e67e22' : '#3498db'};">
                <div class="bill-card-header">
                    <div>
                        <strong>${this.escape(b.bill_no || '#' + b.id)}</strong>
                        <span class="badge ${isHigh ? 'action-final_approve' : 'action-archive'}" style="margin-left: 8px;">
                            ${isHigh ? '🔴 大额（需双签）' : '🟢 小额'}
                        </span>
                    </div>
                    <div><strong style="color: #2c3e50; font-size: 18px;">¥${this.formatMoney(b.total_amount)}</strong></div>
                </div>
                <div class="bill-card-body">
                    <div class="bill-info-row">
                        <span>报销人：${this.escape(b.user_name || '-')}</span>
                        <span>项目：${this.escape(b.project_name || '-')}</span>
                        <span>出差：${b.travel_start_date || '-'} → ${b.travel_end_date || '-'}</span>
                    </div>
                    <div class="bill-info-row">
                        <span>稽核员：${this.escape(b.auditor_name || '-')}</span>
                        <span>稽核意见：${this.escape(b.auditor_comment || '-')}</span>
                    </div>
                </div>
                <div class="bill-card-footer">
                    <button class="btn btn-primary" data-action="final-approve" data-bill-id="${b.id}">
                        ✓ 终审通过
                    </button>
                    <button class="btn" data-action="final-reject" data-bill-id="${b.id}">
                        ✗ 终审驳回
                    </button>
                </div>
            </div>
        `;
    },

    async _doFinalAudit(billId, decision) {
        let comment = '';
        if (decision === 'approve') {
            // 检查是否大额 → 选第二签人
            try {
                const r = await this.api.get(`/api/bills/${billId}`);
                const bill = r.data;
                if (parseFloat(bill.total_amount || 0) >= 100000) {
                    // 列出可选财务
                    const usersRes = await this.api.get('/api/users/list?role=finance');
                    const finances = (usersRes.data || []).filter(u => u.id !== this.currentUser.user_id);
                    if (finances.length === 0) {
                        alert('没有可选的第二签人（需至少 2 名财务账号）');
                        return;
                    }
                    const options = finances.map(u => `<option value="${u.id}">${this.escape(u.real_name)} (${u.username})</option>`).join('');
                    const dualSingerId = prompt(
                        `大额报销需双签。\n请输入第二签人 ID：\n\n${finances.map(u => `${u.id} - ${u.real_name} (${u.username})`).join('\n')}`
                    );
                    if (!dualSingerId) return;
                    const dualSingerIdNum = parseInt(dualSingerId);
                    if (!finances.find(u => u.id === dualSingerIdNum)) {
                        alert('非法的第二签人 ID');
                        return;
                    }
                    comment = prompt('终审意见：') || '';
                    const result = await this.api.post(`/api/bills/${billId}/finance-audit`, {
                        decision: 'approve',
                        comment: comment,
                        dual_signer_id: dualSingerIdNum,
                    });
                    if (result.code !== 0) {
                        alert('终审失败：' + result.message);
                        return;
                    }
                    alert('已提交终审，等待第二签人批准');
                    this._view_final_audit(document.getElementById('content'));
                    return;
                }
            } catch (e) {
                // 忽略，继续
            }
            comment = prompt('终审意见：') || '';
        } else {
            comment = prompt('驳回意见（≥10 字符）：');
            if (!comment || comment.length < 10) {
                alert('驳回意见至少 10 个字符');
                return;
            }
        }

        const r = await this.api.post(`/api/bills/${billId}/finance-audit`, {
            decision: decision,
            comment: comment,
        });
        if (r.code !== 0) {
            alert('操作失败：' + r.message);
            return;
        }
        alert(decision === 'approve' ? '终审通过' : '已驳回');
        this._view_final_audit(document.getElementById('content'));
    },

    // ============= 视图：待双签工作台（D3 决策） =============
    async _view_pending_dual_sign(c) {
        const r = await this.api.get('/api/bills/pending-dual-sign');
        const bills = r.data || [];

        c.innerHTML = `
            <div class="card">
                <h3>待双签工作台（D3 决策）</h3>
                <p class="hint">
                    这里是主财务已 approve、等待你（指定的第二签人）终审批准的大额单据。<br/>
                    <strong>操作流程：</strong> 点击单据 → 查看详情 → 同意（终审通过自动归档）或 拒绝（必填 ≥10 字符原因）。
                </p>
                <div class="stat-grid">
                    <div class="stat-card" style="background: linear-gradient(135deg, #e67e22 0%, #d35400 100%); color: white;">
                        <div class="stat-num">${bills.length}</div>
                        <div class="stat-label" style="color: rgba(255,255,255,0.9);">待我双签</div>
                    </div>
                </div>
            </div>
            <div id="dual-sign-list"></div>
        `;

        const list = document.getElementById('dual-sign-list');
        if (bills.length === 0) {
            list.innerHTML = '<div class="card"><p class="placeholder">✓ 当前没有待你双签的单据</p></div>';
            return;
        }

        list.innerHTML = bills.map(b => `
            <div class="bill-card" style="border-left: 4px solid #e67e22;">
                <div class="bill-card-header">
                    <div>
                        <strong>${this.escape(b.bill_no || '#' + b.id)}</strong>
                        <span class="badge action-override" style="margin-left: 8px;">⏳ 待双签</span>
                    </div>
                    <div><strong style="color: #2c3e50; font-size: 18px;">¥${this.formatMoney(b.total_amount)}</strong></div>
                </div>
                <div class="bill-card-body">
                    <div class="bill-info-row">
                        <span>主财务：${b.finance_auditor_id ? 'ID #' + b.finance_auditor_id : '-'}</span>
                        <span>主审时间：${b.finance_audit_at ? this.formatDate(b.finance_audit_at) : '-'}</span>
                    </div>
                    <div class="bill-info-row">
                        <span>主审意见：<em>${this.escape(b.finance_comment || '-')}</em></span>
                    </div>
                </div>
                <div class="bill-card-footer">
                    <button class="btn btn-primary" data-action="dual-approve" data-bill-id="${b.id}">
                        ✓ 同意终审
                    </button>
                    <button class="btn" data-action="dual-reject" data-bill-id="${b.id}">
                        ✗ 拒绝
                    </button>
                    <button class="btn-sm" data-action="view-bill" data-bill-id="${b.id}">
                        📄 查看详情
                    </button>
                </div>
            </div>
        `).join('');

        // 绑定事件
        c.querySelectorAll('[data-action="dual-approve"]').forEach(btn => {
            btn.onclick = () => this._doDualSign(parseInt(btn.dataset.billId), 'approve');
        });
        c.querySelectorAll('[data-action="dual-reject"]').forEach(btn => {
            btn.onclick = () => this._doDualSign(parseInt(btn.dataset.billId), 'reject');
        });
        c.querySelectorAll('[data-action="view-bill"]').forEach(btn => {
            btn.onclick = () => this._view_bills(document.getElementById('content'), parseInt(btn.dataset.billId));
        });
    },

    async _doDualSign(billId, decision) {
        let comment = '';
        if (decision === 'reject') {
            comment = prompt('拒绝原因（≥10 字符）：');
            if (!comment || comment.length < 10) {
                alert('拒绝原因至少 10 个字符');
                return;
            }
        } else {
            comment = prompt('双签意见（可选）：') || '';
        }

        const r = await this.api.post(`/api/bills/${billId}/dual-sign`, {
            decision: decision,
            comment: comment,
        });
        if (r.code !== 0) {
            alert('操作失败：' + r.message);
            return;
        }
        alert(decision === 'approve' ? '✓ 双签通过，已归档' : '✗ 已驳回');
        this._view_pending_dual_sign(document.getElementById('content'));
    },

    // ============= 视图：强制修改历史（D3 override） =============
    async _view_override_history(c) {
        const r = await this.api.get('/api/audit/research/list?action=override&limit=200');
        const items = r.data || [];

        c.innerHTML = `
            <div class="card">
                <h3>强制修改历史（D3 决策）</h3>
                <p class="hint">
                    列出所有 override 操作的审计记录。每条记录含操作人、时间、IP、原因、状态变更。
                    用于内部审计与外部合规检查。
                </p>
            </div>
            <div class="card">
                ${items.length === 0 ? '<p class="placeholder">无强制修改记录</p>' : `
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>时间</th>
                                <th>单据</th>
                                <th>操作人</th>
                                <th>状态变更</th>
                                <th>IP</th>
                                <th>原因</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${items.map(i => `
                                <tr>
                                    <td>${this.formatDate(i.created_at)}</td>
                                    <td><a href="#" onclick="App._viewBillDetail(${i.bill_id}); return false;">#${i.bill_id}</a></td>
                                    <td>${this.escape(i.auditor_name || '-')}</td>
                                    <td><code>${i.original_status} → ${i.new_status}</code></td>
                                    <td><code>${i.ip_address || '-'}</code></td>
                                    <td><small>${this.escape((i.reason || '-').substring(0, 80))}</small></td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `}
            </div>
        `;
    },

    // ============= 视图：项目 =============
    async _view_projects(c) {
        const r = await this.api.get('/api/projects/list');
        const projects = r.data || [];
        const canManage = ['finance', 'auditor'].includes(this.currentUser.role);
        c.innerHTML = `
            <div class="toolbar">
                <button class="btn btn-primary" onclick="App.showCreateProject()">+ 新建项目</button>
                ${canManage ? '<button class="btn" onclick="App._view_agents()">🤝 代理关系管理</button>' : ''}
            </div>
            <div class="card">
                ${projects.length ? `
                    <table class="data-table">
                        <thead>
                            <tr><th>代码</th><th>名称</th><th>起止</th><th>主审财务</th><th>状态</th>${canManage ? '<th>操作</th>' : ''}</tr>
                        </thead>
                        <tbody>
                            ${projects.map(p => `
                                <tr>
                                    <td>${this.escape(p.project_code)}</td>
                                    <td>${this.escape(p.project_name)}</td>
                                    <td>${this.formatDate(p.start_date)} ~ ${this.formatDate(p.end_date)}</td>
                                    <td>${p.finance_auditor_id || '-'}</td>
                                    <td>${p.status}</td>
                                    ${canManage ? `<td><button class="btn btn-sm" onclick="App._view_project_agents(${p.id}, '${this.escape(p.project_name)}')">🤝 代填</button></td>` : ''}
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                ` : '<p class="placeholder">暂无项目</p>'}
            </div>
        `;
    },

    async _view_project_agents(projectId, projectName) {
        const c = document.getElementById('view-content');
        c.innerHTML = '<p class="placeholder">加载中...</p>';
        const [r, auditorR, allReimbR] = await Promise.all([
            this.api.get(`/api/agents/by-project/${projectId}`),
            this.api.get('/api/users/list?role=auditor'),
            this.api.get('/api/users/list?role=reimburser'),
        ]);
        if (r.code !== 0) { c.innerHTML = '<p class="error">加载失败：' + r.message + '</p>'; return; }
        const data = r.data;
        const allReimbMap = {};
        (allReimbR.data || []).forEach(u => allReimbMap[u.id] = u);

        c.innerHTML = `
            <div class="card">
                <h3>🤝 项目代填管理 - ${this.escape(projectName)}</h3>
                <p class="hint">为这个项目设置稽核员→报销员的代填关系。代填关系建立后：
                <br/>① 该报销员在此项目下的报销/考勤由稽核员代办
                <br/>② 状态变化通知自动抄送稽核员（标题前缀"代 [姓名]"）
                <br/>③ 报销员此项目下不需要登录客户端</p>
                <button class="btn" onclick="App.navigate('projects')">← 返回项目列表</button>
            </div>
            <div class="card">
                <h4>当前代填关系 (${data.active_auths.length})</h4>
                ${data.active_auths.length === 0 ? '<p class="hint">暂无</p>' : `
                    <table class="data-table">
                        <thead><tr><th>稽核员</th><th>报销员</th><th>模式</th><th>操作</th></tr></thead>
                        <tbody>
                            ${data.active_auths.map(a => `
                                <tr>
                                    <td>${this.escape(a.auditor_name)}</td>
                                    <td>${this.escape(a.reimburser_name)}（${this.escape(a.reimburser_username)}）</td>
                                    <td>${a.agent_mode}</td>
                                    <td><button class="btn btn-sm btn-danger" onclick="App._revokeAgent(${a.id})">撤销</button></td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `}
            </div>
            <div class="card">
                <h4>添加代填关系</h4>
                <form onsubmit="return App._setupAgent(event, ${projectId})">
                    <div class="form-group">
                        <label>稽核员</label>
                        <select id="ag-auditor" required>
                            <option value="">-- 选择稽核员 --</option>
                            ${(auditorR.data || []).map(u => `<option value="${u.id}">${this.escape(u.real_name)}（${this.escape(u.username)}）</option>`).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>报销员（必须先绑定到此项目）</label>
                        <select id="ag-reimburser" required>
                            <option value="">-- 选择报销员 --</option>
                            ${(data.all_reimbursers || []).map(u => `<option value="${u.id}">${this.escape(u.real_name)}（${this.escape(u.username)}）${u.need_agent ? ' ⚠未代理' : ''}</option>`).join('')}
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary">建立代填</button>
                </form>
                <p class="hint">${data.unassigned_reimbursers.filter(u => u.need_agent).length} 个报销员未设置代填</p>
            </div>
        `;
    },

    async _setupAgent(e, projectId) {
        e.preventDefault();
        const r = await this.api.post('/api/agents/setup', {
            agent_id: parseInt(document.getElementById('ag-auditor').value),
            be_agent_id: parseInt(document.getElementById('ag-reimburser').value),
            project_id: projectId,
            agent_mode: 'full',
        });
        alert(r.message);
        if (r.code === 0) this._view_project_agents(projectId, document.querySelector('.card h3').textContent.replace('🤝 项目代填管理 - ', ''));
        return false;
    },

    async _revokeAgent(authId) {
        if (!confirm('确认撤销该代填关系？')) return;
        const r = await this.api.delete('/api/agents/' + authId);
        alert(r.message);
        if (r.code === 0) {
            // 重新加载项目代填页
            const projectId = arguments[0] || null;
            // 简化：从 hash 拿
            location.reload();
        }
    },

    async _view_agents() {
        const c = document.getElementById('view-content');
        c.innerHTML = '<p class="placeholder">加载中...</p>';
        const r = await this.api.get('/api/agents/list');
        const items = r.data || [];
        c.innerHTML = `
            <div class="card">
                <h3>🤝 代理关系管理</h3>
                <p class="hint">查看所有当前生效的代填关系。要设置新关系，请进入「项目台账」→ 选择项目 → 点击"代填"按钮。</p>
                <table class="data-table">
                    <thead>
                        <tr><th>稽核员</th><th>报销员</th><th>项目</th><th>模式</th><th>起始日期</th><th>状态</th><th>操作</th></tr>
                    </thead>
                    <tbody>
                        ${items.length === 0 ? '<tr><td colspan="7" class="placeholder">暂无代理关系</td></tr>' :
                            items.map(it => `
                                <tr>
                                    <td>${this.escape(it.auditor_name || '-')}</td>
                                    <td>${this.escape(it.reimburser_name || '-')}</td>
                                    <td>${this.escape(it.project_name || '-')}</td>
                                    <td>${it.agent_mode || '-'}</td>
                                    <td>${it.auth_start_date || '-'}</td>
                                    <td><span class="badge badge-success">${it.status}</span></td>
                                    <td><button class="btn btn-sm btn-danger" onclick="App._revokeAgentDirect(${it.id})">撤销</button></td>
                                </tr>
                            `).join('')}
                    </tbody>
                </table>
            </div>
            <div class="card">
                <h3>📊 模式 C 部署概览</h3>
                <p class="hint">按报销员查看其模式 C 状态（基于项目覆盖度）</p>
                <div id="mode-c-summary"></div>
            </div>
        `;
        // 加载模式 C 状态
        const mcr = await this.api.get('/api/agents/mode-c-status');
        const items2 = mcr.data || [];
        const modeLabel = {
            'agent_c': '<span style="background: #f39c12; color: white; padding: 1px 6px; border-radius: 3px; font-size: 11px;">完全模式 C</span> 全部项目已代理',
            'partial': '<span style="background: #e67e22; color: white; padding: 1px 6px; border-radius: 3px; font-size: 11px;">部分</span> 部分项目代理',
            'self': '<span style="background: #3498db; color: white; padding: 1px 6px; border-radius: 3px; font-size: 11px;">自助</span> 全部自助',
            'orphan': '<span style="background: #95a5a6; color: white; padding: 1px 6px; border-radius: 3px; font-size: 11px;">未绑定</span> 无项目',
        };
        document.getElementById('mode-c-summary').innerHTML = items2.length === 0 ? '<p class="hint">无报销员</p>' :
            `<table class="data-table">
                <thead><tr><th>姓名</th><th>模式</th><th>项目数</th><th>已代理</th></tr></thead>
                <tbody>${items2.map(u => `<tr>
                    <td>${this.escape(u.real_name)}（${this.escape(u.username)}）</td>
                    <td>${modeLabel[u.mode] || u.mode}</td>
                    <td>${u.total_projects}</td>
                    <td>${u.authed_projects}</td>
                </tr>`).join('')}</tbody>
            </table>`;
    },

    async _revokeAgentDirect(authId) {
        if (!confirm('确认撤销？')) return;
        const r = await this.api.delete('/api/agents/' + authId);
        alert(r.message);
        if (r.code === 0) this._view_agents();
    },

    showCreateProject() {
        document.getElementById('view-content').innerHTML = `
            <div class="card">
                <h3>新建项目</h3>
                <form onsubmit="return App.doCreateProject(event)">
                    <div class="form-group">
                        <label>项目代码</label>
                        <input type="text" id="proj-code" required>
                    </div>
                    <div class="form-group">
                        <label>项目名称</label>
                        <input type="text" id="proj-name" required>
                    </div>
                    <div class="form-group">
                        <label>类型</label>
                        <select id="proj-type">
                            <option value="普通">普通</option>
                            <option value="专案">专案</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>开始日期</label>
                        <input type="date" id="proj-start" required>
                    </div>
                    <div class="form-group">
                        <label>结束日期</label>
                        <input type="date" id="proj-end" required>
                    </div>
                    <div class="action-buttons">
                        <button type="submit" class="btn btn-primary">创建</button>
                        <button type="button" class="btn" onclick="App.navigate('projects')">取消</button>
                    </div>
                </form>
            </div>
        `;
    },

    async doCreateProject(e) {
        e.preventDefault();
        const data = {
            project_code: document.getElementById('proj-code').value,
            project_name: document.getElementById('proj-name').value,
            project_type: document.getElementById('proj-type').value,
            start_date: document.getElementById('proj-start').value,
            end_date: document.getElementById('proj-end').value,
        };
        const r = await this.api.post('/api/projects/create', data);
        alert(r.message);
        if (r.code === 0) this.navigate('projects');
        return false;
    },

    // ============= 视图：人员 =============
    async _view_users(c) {
        const [reimbRes, auditRes, finRes] = await Promise.all([
            this.api.get('/api/users/list?role=reimburser'),
            this.api.get('/api/users/list?role=auditor'),
            this.api.get('/api/users/list?role=finance'),
        ]);
        const canBuild = ['finance', 'auditor'].includes(this.currentUser.role);
        // v2.10.0 模式 C：批量查询报销员代理状态
        const reimbStatus = {};
        if (canBuild && reimbRes.data) {
            for (const u of reimbRes.data) {
                try {
                    const r = await this.api.get(`/api/distribution/check-reimburser/${u.id}`);
                    reimbStatus[u.id] = r.data;
                } catch (e) { reimbStatus[u.id] = { mode: 'self', need_package: true }; }
            }
        }
        this._reimbStatus = reimbStatus;
        c.innerHTML = `
            <div class="toolbar">
                <button class="btn btn-primary" onclick="App.showCreateUser()">+ 新建人员</button>
                <button class="btn" onclick="App._view_client_distribution()">📦 客户端分发</button>
            </div>
            <div class="card">
                <h3>财务账号</h3>
                ${this._renderUserTable(finRes.data, 'finance', canBuild && this.currentUser.role === 'finance')}
                <h3>稽核员</h3>
                ${this._renderUserTable(auditRes.data, 'auditor', canBuild && this.currentUser.role === 'finance')}
                <h3>报销人 ${this._renderReimbLegend(reimbStatus)}</h3>
                ${this._renderUserTable(reimbRes.data, 'reimburser', canBuild)}
            </div>
        `;
    },

    _renderReimbLegend(statusMap) {
        const cCount = Object.values(statusMap).filter(s => s.mode === 'agent_c').length;
        const sCount = Object.values(statusMap).filter(s => s.mode === 'self').length;
        if (cCount === 0 && sCount === 0) return '';
        return `<small style="margin-left: 12px; color: #7f8c8d;">
            <span style="background: #f39c12; color: white; padding: 1px 6px; border-radius: 3px; font-size: 11px;">模式 C 全代填 ${cCount}</span>
            <span style="background: #3498db; color: white; padding: 1px 6px; border-radius: 3px; font-size: 11px; margin-left: 4px;">自助模式 ${sCount}</span>
        </small>`;
    },

    _renderUserTable(users, role, canBuild) {
        if (!users || !users.length) return '<p class="placeholder">无</p>';
        const isReimb = role === 'reimburser';
        return `
            <table class="data-table">
                <thead><tr><th>账号</th><th>姓名</th><th>部门</th><th>状态</th>${isReimb && this._reimbStatus ? '<th>部署模式</th>' : ''}${canBuild ? '<th>操作</th>' : ''}</tr></thead>
                <tbody>
                    ${users.map(u => {
                        const status = isReimb && this._reimbStatus ? this._reimbStatus[u.id] : null;
                        const modeCell = status ? (status.mode === 'agent_c'
                            ? `<span style="background: #f39c12; color: white; padding: 1px 6px; border-radius: 3px; font-size: 11px;">模式 C</span> 代 ${this.escape(status.proxy_auditor?.real_name || '?')}`
                            : '<span style="background: #3498db; color: white; padding: 1px 6px; border-radius: 3px; font-size: 11px;">自助</span>') : '';
                        return `<tr>
                            <td>${this.escape(u.username)}</td>
                            <td>${this.escape(u.real_name)}</td>
                            <td>${this.escape(u.department || '-')}</td>
                            <td>${u.account_status}</td>
                            ${status ? `<td>${modeCell}</td>` : ''}
                            ${canBuild ? `<td>
                                ${role === 'auditor' ? `<button class="btn btn-sm btn-primary" onclick="App._buildClient('auditor', ${u.id}, '${this.escape(u.real_name)}')">📦 下发稽核员端</button>` : ''}
                                ${isReimb ? (status && status.mode === 'agent_c'
                                    ? `<button class="btn btn-sm" disabled title="${this.escape(status.message || '')}">✓ 模式 C（已代理）</button>`
                                    : `<button class="btn btn-sm btn-primary" onclick="App._buildClient('reimburser', ${u.id}, '${this.escape(u.real_name)}')">📦 下发报销员端</button>`
                                ) : ''}
                            </td>` : ''}
                        </tr>`;
                    }).join('')}
                </tbody>
            </table>
        `;
    },

    async _buildClient(role, userId, name) {
        const roleName = role === 'auditor' ? '稽核员' : '报销员';
        if (!confirm(`确认为【${name}】生成${roleName}绿色客户端包？\n\n将按角色裁剪数据：\n- ${roleName}可见的单据\n- 相关项目/人员/配置\n- 自动打包为 ~150MB zip\n\n打包过程可能需要 10-30 秒`)) return;
        const url = role === 'auditor'
            ? `/api/distribution/build/auditor/${userId}`
            : `/api/distribution/build/reimburser/${userId}`;
        const r = await this.api.post(url, {});
        if (r.code !== 0) {
            alert('生成失败：' + r.message);
            return;
        }
        const d = r.data;
        alert(`✓ ${r.message}\n\n数据范围：${d.data_scope.users} 用户 / ${d.data_scope.projects} 项目 / ${d.data_scope.bills} 单据\n包大小：${d.zip_size_mb} MB\n\n请点击"客户端分发"页面下载。`);
        this._view_client_distribution();
    },

    async _view_client_distribution() {
        const c = document.getElementById('view-content');
        c.innerHTML = '<p class="placeholder">加载中...</p>';
        const r = await this.api.get('/api/distribution/list');
        const items = (r.data && r.data.items) || [];
        const fmtSize = mb => mb >= 1024 ? (mb/1024).toFixed(2) + ' GB' : mb + ' MB';
        c.innerHTML = `
            <div class="card">
                <h3>📦 客户端分发</h3>
                <p class="hint">为下级用户自动生成带数据的绿色客户端包。流程：选用户 → 一键生成 → 下载 zip → 对方解压运行。</p>
                <table class="data-table">
                    <thead>
                        <tr><th>文件名</th><th>大小</th><th>生成时间</th><th>操作</th></tr>
                    </thead>
                    <tbody>
                        ${items.length === 0 ? '<tr><td colspan="4" class="placeholder">暂无已生成的客户端包</td></tr>' :
                            items.map(it => {
                                const dt = new Date(it.created_at * 1000);
                                const dateStr = dt.toLocaleString('zh-CN');
                                return `<tr>
                                    <td><code>${this.escape(it.name)}</code></td>
                                    <td>${fmtSize(it.size_mb)}</td>
                                    <td>${dateStr}</td>
                                    <td>
                                        <a class="btn btn-sm btn-primary" href="/api/distribution/download/${encodeURIComponent(it.name)}" target="_blank">📥 下载</a>
                                        <button class="btn btn-sm btn-danger" onclick="App._deleteZip('${this.escape(it.name)}')">删除</button>
                                    </td>
                                </tr>`;
                            }).join('')}
                    </tbody>
                </table>
            </div>
            <div class="card">
                <h3>📖 使用流程</h3>
                <ol style="line-height: 1.8; margin-left: 20px;">
                    <li><strong>创建下级账号</strong>：在「人员账号」页面新建稽核员/报销员</li>
                    <li><strong>设置代理关系</strong>：如需模式 C（稽核员代填），在「报销人管理」里绑定 agent_auth</li>
                    <li><strong>一键生成包</strong>：在该用户行点「📦 下发xxx端」按钮（数据按角色自动裁剪）</li>
                    <li><strong>下载 zip</strong>：在本页面点击下载（约 150MB，包含 Python 解释器+依赖+裁剪后数据）</li>
                    <li><strong>分发包</strong>：通过 U 盘 / 网盘 / 邮件 / 中心节点同步给下级用户</li>
                    <li><strong>对方部署</strong>：解压 → 双击「启动xxx版.bat」→ 首次启动自动建库 → 登录使用</li>
                </ol>
                <h4 style="margin-top: 16px;">部署模式（v2.10.0 模式 C 混合）</h4>
                <table class="data-table">
                    <thead><tr><th>模式</th><th>说明</th><th>是否需要客户端</th><th>典型场景</th></tr></thead>
                    <tbody>
                        <tr><td>模式 A 精简</td><td>只部署 财务 + 稽核员 客户端</td><td>报销员无需</td><td>报销员少、稽核员富余</td></tr>
                        <tr style="background: #fff8e1;">
                            <td><strong>模式 C 混合（推荐）</strong></td>
                            <td>按报销员情况：自助的给客户端；被代理的不发</td>
                            <td>看 agent_auth 关系</td>
                            <td>同一系统下两类报销员共存</td>
                        </tr>
                        <tr><td>模式 B 完整</td><td>三方各自登录</td><td>都需要</td><td>报销员多、自助意识强</td></tr>
                    </tbody>
                </table>
                <p class="hint" style="margin-top: 8px;">📌 模式 C 关键：<strong>报销员被稽核员绑定（agent_auth）后</strong>，系统自动：<br/>
                ① 不生成该报销员的客户端包<br/>
                ② 状态变化通知同步发给稽核员（标题前缀"代 [报销员名]"）<br/>
                ③ 稽核员可代填考勤 / 报销 / 查询</p>
            </div>
        `;
    },

    async _deleteZip(name) {
        if (!confirm('确认删除「' + name + '」？此操作不可恢复。')) return;
        const r = await this.api.post('/api/distribution/delete/' + encodeURIComponent(name), {});
        if (r.code !== 0) { alert('删除失败：' + r.message); return; }
        this._view_client_distribution();
    },

    showCreateUser() {
        document.getElementById('view-content').innerHTML = `
            <div class="card">
                <h3>新建人员</h3>
                <form onsubmit="return App.doCreateUser(event)">
                    <div class="form-group">
                        <label>账号</label>
                        <input type="text" id="user-username" required>
                    </div>
                    <div class="form-group">
                        <label>姓名</label>
                        <input type="text" id="user-realname" required>
                    </div>
                    <div class="form-group">
                        <label>角色</label>
                        <select id="user-role">
                            <option value="reimburser">报销人</option>
                            <option value="auditor">稽核员</option>
                            <option value="finance">财务</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>人员类型</label>
                        <select id="user-staff-type">
                            <option value="在编">在编</option>
                            <option value="借调">借调</option>
                            <option value="跟班">跟班</option>
                            <option value="实战练兵">实战练兵</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>部门</label>
                        <input type="text" id="user-dept">
                    </div>
                    <div class="action-buttons">
                        <button type="submit" class="btn btn-primary">创建</button>
                        <button type="button" class="btn" onclick="App.navigate('users')">取消</button>
                    </div>
                </form>
            </div>
        `;
    },

    async doCreateUser(e) {
        e.preventDefault();
        const data = {
            username: document.getElementById('user-username').value,
            real_name: document.getElementById('user-realname').value,
            role: document.getElementById('user-role').value,
            staff_type: document.getElementById('user-staff-type').value,
            department: document.getElementById('user-dept').value,
        };
        const r = await this.api.post('/api/users/create', data);
        alert(r.message);
        if (r.code === 0) this.navigate('users');
        return false;
    },

    // ============= 视图：新建报销 =============
    async _view_new_bill(c) {
        const r = await this.api.get('/api/projects/list');
        const projects = r.data || [];
        c.innerHTML = `
            <div class="card">
                <h3>新建报销单</h3>
                <form onsubmit="return App.doCreateBill(event)">
                    <div class="form-group">
                        <label>项目</label>
                        <select id="bill-project" required>
                            ${projects.map(p => `<option value="${p.id}">${this.escape(p.project_code)} - ${this.escape(p.project_name)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>出发日期</label>
                        <input type="date" id="bill-start" required>
                    </div>
                    <div class="form-group">
                        <label>返回日期</label>
                        <input type="date" id="bill-end" required>
                    </div>
                    <div class="form-group">
                        <label>目的地</label>
                        <input type="text" id="bill-dest" required>
                    </div>
                    <div class="form-group">
                        <label>交通费</label>
                        <input type="number" id="bill-transport" value="0" min="0" step="0.01">
                    </div>
                    <div class="form-group">
                        <label>住宿费</label>
                        <input type="number" id="bill-accom" value="0" min="0" step="0.01">
                    </div>
                    <div class="form-group">
                        <label>其他费</label>
                        <input type="number" id="bill-other" value="0" min="0" step="0.01">
                    </div>
                    <div class="action-buttons">
                        <button type="submit" class="btn btn-primary">创建报销单</button>
                    </div>
                </form>
            </div>
        `;
    },

    async doCreateBill(e) {
        e.preventDefault();
        const data = {
            user_id: this.currentUser.user_id,
            project_id: parseInt(document.getElementById('bill-project').value),
            bill_type: 'personal',
            travel_start_date: document.getElementById('bill-start').value,
            travel_end_date: document.getElementById('bill-end').value,
            destination: document.getElementById('bill-dest').value,
            transport_fee: parseFloat(document.getElementById('bill-transport').value) || 0,
            accommodation_fee: parseFloat(document.getElementById('bill-accom').value) || 0,
            other_fee: parseFloat(document.getElementById('bill-other').value) || 0,
        };

        // 防重复预检
        const dup = await this.api.post('/api/bills/check-duplicate', {
            user_id: this.currentUser.user_id,
            project_id: data.project_id,
            travel_start_date: data.travel_start_date,
            travel_end_date: data.travel_end_date,
        });
        if (dup.data.status === 'block') {
            alert('防重复拦截：' + dup.data.message);
            return false;
        }
        if (dup.data.status === 'warning') {
            if (!confirm('警告：' + dup.data.message + '，是否继续？')) return false;
        }

        const r = await this.api.post('/api/bills/create', data);
        if (r.code === 0) {
            alert('创建成功，单号：' + r.data.bill_no);
            this.navigate('my-bills');
        } else {
            alert(r.message);
        }
        return false;
    },

    // ============= 视图：通知中心（v2.2.0） =============
    async _view_notifications(c) {
        const r = await this.api.get('/api/notifications/list?limit=100');
        const items = r.data || [];
        const unreadCount = r.unread_count || 0;

        c.innerHTML = `
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <h3>🔔 通知中心（${items.length}）</h3>
                    <div>
                        <span class="badge" style="background: #e74c3c; color: white; margin-right: 8px;">未读 ${unreadCount}</span>
                        ${unreadCount > 0 ? `<button class="btn btn-primary" onclick="App._doMarkAllRead()">全部标为已读</button>` : ''}
                    </div>
                </div>
                <p class="hint">单据状态变更（通过/驳回/双签/强制修改）会自动发送通知到这里。</p>
            </div>
            <div class="card">
                ${items.length === 0 ? '<p class="placeholder">暂无通知</p>' : `
                    <div class="notification-list">
                        ${items.map(n => this._renderNotification(n)).join('')}
                    </div>
                `}
            </div>
            <div class="card">
                <h3>📤 发送通知（${this.currentUser.role === 'reimburser' ? '不可用' : '财务/稽核员/管理员'}）</h3>
                ${this.currentUser.role === 'reimburser' ? '<p class="placeholder">报销人仅查看自己的通知</p>' : `
                    <form onsubmit="return App._doSendNotification(event)">
                        <div class="form-group">
                            <label>接收人</label>
                            <select id="notif-receiver" required>
                                <option value="">-- 选择接收人 --</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>类型</label>
                            <select id="notif-type">
                                <option value="system">系统通知</option>
                                <option value="bill_approved">已批准</option>
                                <option value="bill_rejected">已驳回</option>
                                <option value="bill_overridden">强制修改</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>标题</label>
                            <input type="text" id="notif-title" maxlength="200" required>
                        </div>
                        <div class="form-group">
                            <label>内容</label>
                            <textarea id="notif-content" rows="4" required></textarea>
                        </div>
                        <div class="form-group">
                            <label>优先级</label>
                            <select id="notif-priority">
                                <option value="low">低</option>
                                <option value="normal" selected>普通</option>
                                <option value="high">高</option>
                                <option value="urgent">紧急</option>
                            </select>
                        </div>
                        <div class="form-message" id="notif-msg"></div>
                        <button type="submit" class="btn btn-primary">发送</button>
                    </form>
                `}
            </div>
        `;

        // 绑定事件
        c.querySelectorAll('[data-action="notif-read"]').forEach(btn => {
            btn.onclick = () => this._doMarkRead(parseInt(btn.dataset.nid));
        });
        c.querySelectorAll('[data-action="notif-delete"]').forEach(btn => {
            btn.onclick = () => this._doDeleteNotification(parseInt(btn.dataset.nid));
        });
        c.querySelectorAll('[data-action="notif-jump-bill"]').forEach(btn => {
            btn.onclick = () => this._view_bill_by_id(parseInt(btn.dataset.billId));
        });

        // 加载接收人列表（仅非报销人）
        if (this.currentUser.role !== 'reimburser') {
            this._loadNotificationReceivers();
        }
    },

    _renderNotification(n) {
        const priorityColor = {
            low: '#95a5a6', normal: '#3498db', high: '#e67e22', urgent: '#e74c3c'
        }[n.priority] || '#3498db';
        const typeLabels = {
            bill_approved: '✓ 已批准',
            bill_rejected: '✗ 已驳回',
            bill_auditor_rejected: '✗ 初审未过',
            bill_pending_dual: '🤝 待双签',
            bill_overridden: '⚡ 强制修改',
            bill_dual_rejected: '⚠ 双签被拒',
            bill_submitted: '📨 已提交',
            bill_auditor_ok: '✓ 初审通过',
            system: 'ℹ 系统通知',
        };
        const typeLabel = typeLabels[n.type] || n.type;
        return `
            <div class="notification-item ${n.is_read ? '' : 'unread'}" data-nid="${n.id}">
                <div class="notif-priority-bar" style="background: ${priorityColor};"></div>
                <div class="notif-content">
                    <div class="notif-header">
                        <span class="notif-type">${typeLabel}</span>
                        ${!n.is_read ? '<span class="badge badge-unread">未读</span>' : ''}
                        <span class="notif-time">${this.formatDate(n.created_at)}</span>
                    </div>
                    <div class="notif-title">${this.escape(n.title)}</div>
                    <div class="notif-body">${this.escape(n.content)}</div>
                    <div class="notif-footer">
                        <span>发送人：${this.escape(n.sender_name || '系统')}</span>
                        ${n.bill_no ? `<span>关联单据：<a href="#" data-action="notif-jump-bill" data-bill-id="${n.bill_id}">${this.escape(n.bill_no)}</a></span>` : ''}
                        <span style="margin-left: auto;">
                            ${!n.is_read ? `<button class="btn-sm" data-action="notif-read" data-nid="${n.id}">标已读</button>` : ''}
                            <button class="btn-sm" data-action="notif-delete" data-nid="${n.id}">删除</button>
                        </span>
                    </div>
                </div>
            </div>
        `;
    },

    async _loadNotificationReceivers() {
        try {
            const r = await this.api.get('/api/users/list');
            const users = (r.data || []).filter(u => u.id !== this.currentUser.user_id);
            const sel = document.getElementById('notif-receiver');
            if (!sel) return;
            sel.innerHTML = '<option value="">-- 选择接收人 --</option>' +
                users.map(u => `<option value="${u.id}">${this.escape(u.real_name)} (${u.username} - ${this._roleLabel(u.role)})</option>`).join('');
        } catch (e) {
            console.error('loadNotificationReceivers', e);
        }
    },

    _roleLabel(role) {
        return { finance: '财务', auditor: '稽核员', reimburser: '报销人', admin: '管理员' }[role] || role;
    },

    async _doMarkRead(nid) {
        const r = await this.api.post(`/api/notifications/${nid}/read`);
        if (r.code === 0) {
            this._view_notifications(document.getElementById('content'));
            this._updateUnreadBadge();
        }
    },

    async _doMarkAllRead() {
        if (!confirm('确认标记所有通知为已读？')) return;
        const r = await this.api.post('/api/notifications/read-all');
        if (r.code === 0) {
            alert(`已标记 ${r.data.count} 条`);
            this._view_notifications(document.getElementById('content'));
            this._updateUnreadBadge();
        }
    },

    async _doDeleteNotification(nid) {
        if (!confirm('确认删除此通知？')) return;
        const r = await this.api.del(`/api/notifications/${nid}`);
        if (r.code === 0) {
            this._view_notifications(document.getElementById('content'));
            this._updateUnreadBadge();
        }
    },

    async _doSendNotification(ev) {
        ev.preventDefault();
        const user_id = parseInt(document.getElementById('notif-receiver').value);
        const type = document.getElementById('notif-type').value;
        const title = document.getElementById('notif-title').value.trim();
        const content = document.getElementById('notif-content').value.trim();
        const priority = document.getElementById('notif-priority').value;
        const msg = document.getElementById('notif-msg');
        if (!user_id) { msg.textContent = '请选择接收人'; msg.className = 'form-message error'; return; }
        if (!title) { msg.textContent = '请输入标题'; msg.className = 'form-message error'; return; }
        if (!content) { msg.textContent = '请输入内容'; msg.className = 'form-message error'; return; }
        const r = await this.api.post('/api/notifications/send', {
            user_id, type, title, content, priority,
        });
        if (r.code === 0) {
            msg.textContent = '已发送'; msg.className = 'form-message success';
            document.getElementById('notif-title').value = '';
            document.getElementById('notif-content').value = '';
            setTimeout(() => this._view_notifications(document.getElementById('content')), 800);
        } else {
            msg.textContent = r.message; msg.className = 'form-message error';
        }
    },

    async _view_bill_by_id(billId) {
        if (this.currentUser.role === 'finance') this._view_bills(document.getElementById('content'));
        else if (this.currentUser.role === 'auditor') this._view_all_bills(document.getElementById('content'));
        else this._view_my_bills(document.getElementById('content'));
        setTimeout(() => this.viewBill(billId), 300);
    },

    // 更新顶部未读数（启动时 + 每次进入新视图后）
    async _updateUnreadBadge() {
        try {
            const r = await this.api.get('/api/notifications/unread-count');
            const count = r.data?.unread_count || 0;
            const el = document.getElementById('topbar-unread');
            if (el) {
                el.textContent = count > 99 ? '99+' : count;
                el.style.display = count > 0 ? 'inline-block' : 'none';
            }
        } catch (e) { /* ignore */ }
    },

    // ============= 视图：数据导入向导（v2.3.0） =============
    async _view_data_import(c) {
        // 步骤：1=选类型+上传 2=预览 3=完成
        c.innerHTML = `
            <div class="card">
                <h3>📥 数据导入向导</h3>
                <p class="hint">
                    从 Excel 文件批量导入数据：<strong>用户 / 项目 / 报销标准</strong>。
                    流程：选类型 → 下载模板 → 上传 → 预览校验 → 确认导入。
                </p>
                <div id="di-step1" class="di-step">
                    <h4>步骤 1：选择导入类型 + 下载模板</h4>
                    <div class="form-group">
                        <label>导入类型</label>
                        <select id="di-type" onchange="App._diUpdateTemplate()">
                            <option value="">-- 选择类型 --</option>
                            <option value="user">用户</option>
                            <option value="project">项目</option>
                            <option value="standard">报销标准</option>
                        </select>
                    </div>
                    <div id="di-template-info"></div>
                    <div class="form-group">
                        <label>下载 Excel 模板</label>
                        <button class="btn" id="di-download-btn" onclick="App._diDownloadTemplate()" disabled>
                            📋 下载模板
                        </button>
                    </div>
                    <hr/>
                    <h4>步骤 2：上传文件</h4>
                    <div class="form-group">
                        <label>选择 .xlsx 文件</label>
                        <input type="file" id="di-file" accept=".xlsx">
                    </div>
                    <button class="btn btn-primary" id="di-upload-btn" onclick="App._diUploadPreview()" disabled>
                        🔍 解析并预览
                    </button>
                </div>
                <div id="di-step2" class="di-step" style="display: none;">
                    <h4>步骤 3：预览 & 确认</h4>
                    <div id="di-summary"></div>
                    <div id="di-preview-table"></div>
                    <div class="action-buttons">
                        <button class="btn" onclick="App._diBackToStep1()">← 重新上传</button>
                        <button class="btn btn-primary" onclick="App._diCommit()">✓ 确认导入</button>
                    </div>
                </div>
                <div id="di-step3" class="di-step" style="display: none;">
                    <h4>✓ 导入完成</h4>
                    <div id="di-result"></div>
                    <div class="action-buttons">
                        <button class="btn" onclick="App._view_data_import(document.getElementById('content'))">继续导入</button>
                        <button class="btn" onclick="App._view_data_import_history(document.getElementById('content'))">查看历史</button>
                    </div>
                </div>
            </div>
            <div class="card">
                <h3>📜 导入历史</h3>
                <div id="di-history"></div>
            </div>
        `;

        this._diLoadHistory();
    },

    _diUpdateTemplate() {
        const type = document.getElementById('di-type').value;
        const btn = document.getElementById('di-download-btn');
        btn.disabled = !type;
        document.getElementById('di-template-info').innerHTML = type
            ? `<p class="hint">${this._diTemplateNote(type)}</p>`
            : '';
    },

    _diTemplateNote(type) {
        const notes = {
            user: '📌 用户：必填用户名/姓名/角色/人员类型。角色只能填 finance / auditor / reimburser。',
            project: '📌 项目：必填项目编码/名称/起止日期。主审财务可不填，填则必须存在。',
            standard: '📌 报销标准：必填职务等级/人员类型/补助类型/金额。',
        };
        return notes[type] || '';
    },

    async _diDownloadTemplate() {
        const type = document.getElementById('di-type').value;
        if (!type) return;
        window.open(`/api/data-import/template/${type}`, '_blank');
    },

    async _diUploadPreview() {
        const type = document.getElementById('di-type').value;
        const fileInput = document.getElementById('di-file');
        if (!type) { alert('请选择导入类型'); return; }
        if (!fileInput.files[0]) { alert('请选择文件'); return; }

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('import_type', type);

        const btn = document.getElementById('di-upload-btn');
        btn.disabled = true;
        btn.textContent = '解析中...';

        try {
            const r = await fetch('/api/data-import/preview', {
                method: 'POST',
                body: formData,
                credentials: 'same-origin',
            });
            const result = await r.json();
            if (result.code !== 0) {
                alert('解析失败：' + result.message);
                btn.disabled = false;
                btn.textContent = '🔍 解析并预览';
                return;
            }
            this._diPreviewData = { type, file: fileInput.files[0], ...result.data };
            this._diRenderPreview();
        } catch (e) {
            alert('上传失败：' + e);
        }
        btn.disabled = false;
        btn.textContent = '🔍 解析并预览';
    },

    _diRenderPreview() {
        const d = this._diPreviewData;
        document.getElementById('di-step1').style.display = 'none';
        document.getElementById('di-step2').style.display = 'block';

        const validPct = d.total_rows > 0 ? Math.round(d.valid_count * 100 / d.total_rows) : 0;
        document.getElementById('di-summary').innerHTML = `
            <div class="stat-grid">
                <div class="stat-card">
                    <div class="stat-num">${d.total_rows}</div>
                    <div class="stat-label">总行数</div>
                </div>
                <div class="stat-card stat-card-primary">
                    <div class="stat-num">${d.valid_count}</div>
                    <div class="stat-label">可导入</div>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); color: white;">
                    <div class="stat-num" style="color: white;">${d.invalid_count}</div>
                    <div class="stat-label" style="color: rgba(255,255,255,0.9);">有错误</div>
                </div>
                <div class="stat-card">
                    <div class="stat-num">${validPct}%</div>
                    <div class="stat-label">通过率</div>
                </div>
            </div>
        `;

        // 渲染前 50 行预览
        const cols = this._diGetColumns(d.type);
        const rows = d.rows.slice(0, 50);
        const table = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>行</th>
                        <th>状态</th>
                        ${cols.map(c => `<th>${this.escape(c.label)}</th>`).join('')}
                        <th>错误</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows.map(r => `
                        <tr style="${r._valid ? '' : 'background: #fee;'}">
                            <td>${r._row}</td>
                            <td>${r._valid ? '<span class="badge" style="background: #27ae60; color: white;">✓</span>' : '<span class="badge" style="background: #e74c3c; color: white;">✗</span>'}</td>
                            ${cols.map(c => `<td>${this.escape(String(r[c.key] || ''))}</td>`).join('')}
                            <td><small style="color: #e74c3c;">${this.escape((r._errors || []).join('; '))}</small></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
            ${d.rows.length > 50 ? `<p class="hint">仅显示前 50 行，共 ${d.rows.length} 行</p>` : ''}
        `;
        document.getElementById('di-preview-table').innerHTML = table;
    },

    async _diGetColumns(type) {
        const r = await this.api.get('/api/data-import/templates');
        const tpl = (r.data || []).find(t => t.type === type);
        return tpl ? tpl.columns : [];
    },

    _diBackToStep1() {
        document.getElementById('di-step1').style.display = 'block';
        document.getElementById('di-step2').style.display = 'none';
        this._diPreviewData = null;
    },

    async _diCommit() {
        const d = this._diPreviewData;
        if (!d) return;
        if (d.valid_count === 0) {
            alert('没有可导入的行');
            return;
        }
        if (!confirm(`确认导入 ${d.valid_count} 条数据？\n失败 ${d.invalid_count} 条将记入错误日志但不会回滚成功项。`)) {
            return;
        }

        // 简化 rows：只发 valid 行
        const validRows = d.rows.filter(r => r._valid);

        const r = await this.api.post('/api/data-import/commit', {
            import_type: d.type,
            rows: validRows,
            file_hash: d.file_hash,
            file_size: d.file_size,
            file_name: d.file.name,
        });
        if (r.code !== 0) {
            alert('导入失败：' + r.message);
            return;
        }

        const log = r.data;
        document.getElementById('di-step2').style.display = 'none';
        document.getElementById('di-step3').style.display = 'block';
        const color = { success: '#27ae60', partial: '#e67e22', failed: '#e74c3c' }[log.status] || '#95a5a6';
        document.getElementById('di-result').innerHTML = `
            <div style="padding: 16px; background: #f8f9fa; border-left: 4px solid ${color}; border-radius: 4px;">
                <p><strong>状态：</strong><span style="color: ${color}; font-weight: bold; font-size: 16px;">${log.status.toUpperCase()}</span></p>
                <p><strong>总行数：</strong>${log.total_rows} ｜ <strong>成功：</strong>${log.success_count} ｜ <strong>失败：</strong>${log.failed_count}</p>
                <p class="hint">日志 ID: #${log.id}</p>
            </div>
        `;
    },

    async _diLoadHistory() {
        const r = await this.api.get('/api/data-import/history?limit=10');
        const items = r.data || [];
        const el = document.getElementById('di-history');
        if (items.length === 0) {
            el.innerHTML = '<p class="placeholder">暂无导入记录</p>';
            return;
        }
        el.innerHTML = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>时间</th>
                        <th>类型</th>
                        <th>文件</th>
                        <th>总/成功/失败</th>
                        <th>状态</th>
                    </tr>
                </thead>
                <tbody>
                    ${items.map(i => {
                        const color = { success: '#27ae60', partial: '#e67e22', failed: '#e74c3c' }[i.status] || '#95a5a6';
                        return `<tr>
                            <td>${this.formatDate(i.imported_at)}</td>
                            <td>${i.import_type}</td>
                            <td><small>${this.escape(i.file_name)}</small></td>
                            <td>${i.total_rows}/${i.success_count}/${i.failed_count}</td>
                            <td><span class="badge" style="background: ${color}; color: white;">${i.status}</span></td>
                        </tr>`;
                    }).join('')}
                </tbody>
            </table>
        `;
    },

    _view_data_import_history(c) {
        c.innerHTML = `
            <div class="card">
                <h3>📜 导入历史</h3>
                <div id="di-history-full"></div>
            </div>
        `;
        this._diLoadHistory();
    },

    // ============= 视图：决策链弹窗（D3 增强） =============
    async _viewDecisionChain(billId) {
        const r = await this.api.get(`/api/audit/decision-chain/${billId}`);
        if (r.code !== 0) { alert('加载失败：' + r.message); return; }
        const data = r.data;
        const bill = data.bill;
        // 回放模式：按时间正序（最早 → 最新）
        const chain = (data.chain || []).slice().reverse();

        const chainHtml = chain.length === 0
            ? '<p class="placeholder">暂无决策记录</p>'
            : chain.map((e, i) => this._renderChainItem(e, i)).join('');

        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.id = 'decision-chain-modal';
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 800px;">
                <div class="modal-header">
                    <h3>🔍 决策链 - ${this.escape(bill.bill_no)}</h3>
                    <button class="modal-close" onclick="document.getElementById('decision-chain-modal').remove()">×</button>
                </div>
                <div class="modal-body">
                    <div class="bill-summary">
                        <div class="bill-summary-item">
                            <label>当前状态</label>
                            <span class="status-tag status-${bill.status}">${this._statusText(bill.status)}</span>
                        </div>
                        <div class="bill-summary-item">
                            <label>总金额</label>
                            <span><strong>¥${this.formatMoney(bill.total_amount)}</strong></span>
                        </div>
                        <div class="bill-summary-item">
                            <label>主审财务</label>
                            <span>${bill.finance_auditor_id || '—'}</span>
                        </div>
                        <div class="bill-summary-item">
                            <label>第二签人</label>
                            <span>${bill.finance_dual_signer_id || '—'}</span>
                        </div>
                        <div class="bill-summary-item">
                            <label>双签状态</label>
                            <span>${bill.finance_dual_signed ? '✓ 通过' : '—'}</span>
                        </div>
                    </div>
                    <h4 style="margin-top: 20px;">回放时间线（${chain.length} 条，按时间正序）</h4>
                    ${chain.length > 0 ? `
                    <div class="replay-controls">
                        <button class="btn btn-sm" id="replay-prev" onclick="App._replayStep(-1)">⏮ 上一步</button>
                        <button class="btn btn-sm btn-primary" id="replay-play" onclick="App._replayToggle()">▶ 播放</button>
                        <button class="btn btn-sm" id="replay-next" onclick="App._replayStep(1)">⏭ 下一步</button>
                        <span class="replay-progress"><span id="replay-current">0</span> / ${chain.length}</span>
                        <select id="replay-speed" onchange="App._replaySetSpeed()">
                            <option value="3000">慢（3s/步）</option>
                            <option value="1500" selected>中（1.5s/步）</option>
                            <option value="500">快（0.5s/步）</option>
                        </select>
                        <button class="btn btn-sm" onclick="App._replayReset()">↺ 重放</button>
                    </div>
                    ` : ''}
                    <div class="timeline">
                        ${chainHtml}
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn" onclick="document.getElementById('decision-chain-modal').remove()">关闭</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        // 点击 overlay 关闭
        modal.addEventListener('click', (ev) => {
            if (ev.target === modal) modal.remove();
        });

        // 回放初始化（默认显示全部，可倒带回放）
        if (chain.length > 0) {
            this._replayInit();
            this._replay.total = chain.length;
            this._replay.current = chain.length - 1;  // 默认全亮
            this._replayHighlight();
        }
    },

    // ============= 操作回放（D3 加强） =============
    _replayInit() {
        const self = this;
        this._replay = {
            current: 0,
            playing: false,
            timer: null,
            speed: 1500,
            total: 0,
            play() {
                self._replay.playing = true;
                self._replayTick();
            },
            pause() {
                self._replay.playing = false;
                if (self._replay.timer) {
                    clearTimeout(self._replay.timer);
                    self._replay.timer = null;
                }
            },
            tick() {
                if (self._replay.current < self._replay.total - 1) {
                    self._replay.current++;
                    self._replayHighlight();
                    if (self._replay.playing) {
                        self._replay.timer = setTimeout(self._replay.tick, self._replay.speed);
                    }
                } else {
                    self._replay.pause();
                    const btn = document.getElementById('replay-play');
                    if (btn) btn.textContent = '✓ 完成';
                }
            },
        };
        this._replayTick = this._replay.tick;
    },
    _replayToggle() {
        if (!this._replay) this._replayInit();
        if (this._replay.playing) {
            this._replay.pause();
            const btn = document.getElementById('replay-play');
            if (btn) btn.textContent = '▶ 播放';
        } else {
            this._replay.play();
            const btn = document.getElementById('replay-play');
            if (btn) btn.textContent = '⏸ 暂停';
        }
    },
    _replayStep(delta) {
        if (!this._replay) this._replayInit();
        this._replay.pause();
        document.getElementById('replay-play').textContent = '▶ 播放';
        this._replay.current = Math.max(0, Math.min(this._replay.current + delta, this._replay.total - 1));
        this._replayHighlight();
    },
    _replayReset() {
        if (!this._replay) this._replayInit();
        this._replay.pause();
        this._replay.current = 0;
        document.getElementById('replay-play').textContent = '▶ 播放';
        this._replayHighlight();
    },
    _replaySetSpeed() {
        if (!this._replay) return;
        this._replay.speed = parseInt(document.getElementById('replay-speed').value);
        if (this._replay.playing) {
            this._replay.pause();
            this._replay.play();
        }
    },
    _replayHighlight() {
        const items = document.querySelectorAll('#decision-chain-modal .timeline-item');
        items.forEach((el, i) => {
            el.classList.toggle('replay-active', i <= this._replay.current);
            el.classList.toggle('replay-current', i === this._replay.current);
        });
        const cur = document.getElementById('replay-current');
        if (cur) cur.textContent = (this._replay.current + 1).toString();
        // 滚动到当前
        if (items[this._replay.current]) {
            items[this._replay.current].scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    },
    // 在弹窗创建后初始化回放
    _replaySetup(total) {
        if (!this._replay) this._replayInit();
        this._replay.total = total;
        this._replay.current = total - 1;  // 默认显示全部
        this._replayHighlight();
    },


    // [v2.10.0d 修复] _renderDecisionChainItem 等已禁用（孤儿代码）
    // ============= 视图：终审独立审计（D3 增强：筛选 + 详情弹窗） =============
    async _view_research_audit(c) {
        c.innerHTML = `
            <div class="card">
                <h3>🔍 终审独立审计（D3 决策）</h3>
                <p class="hint">记录 override / dual_sign_request / dual_sign_approve / dual_sign_reject 操作，用于内部审计与外部合规检查。</p>
                <div class="toolbar">
                    <select id="ra-action" onchange="App._applyResearchAuditFilter()">
                        <option value="">全部动作</option>
                        <option value="override">override 强制修改</option>
                        <option value="dual_sign_request">双签请求</option>
                        <option value="dual_sign_approve">双签通过</option>
                        <option value="dual_sign_reject">双签拒绝</option>
                    </select>
                    <input type="date" id="ra-from" placeholder="开始日期" onchange="App._applyResearchAuditFilter()">
                    <input type="date" id="ra-to" placeholder="结束日期" onchange="App._applyResearchAuditFilter()">
                    <button class="btn btn-primary" onclick="App._applyResearchAuditFilter()">查询</button>
                    <button class="btn" onclick="App._resetResearchAuditFilter()">重置</button>
                </div>
            </div>
            <div class="card" id="ra-list">
                <p class="placeholder">加载中...</p>
            </div>
        `;
        await this._applyResearchAuditFilter();
    },

    async _applyResearchAuditFilter() {
        const params = new URLSearchParams();
        const action = document.getElementById('ra-action').value;
        const df = document.getElementById('ra-from').value;
        const dt = document.getElementById('ra-to').value;
        if (action) params.set('action', action);
        if (df) params.set('date_from', df);
        if (dt) params.set('date_to', dt + 'T23:59:59');

        const r = await this.api.get('/api/audit/research/filter?' + params);
        if (r.code !== 0) {
            document.getElementById('ra-list').innerHTML = '<p class="error">加载失败：' + r.message + '</p>';
            return;
        }
        const items = r.data || [];
        const total = r.total || 0;
        const el = document.getElementById('ra-list');
        if (items.length === 0) {
            el.innerHTML = '<p class="placeholder">无匹配记录</p>';
            return;
        }
        el.innerHTML = `
            <p class="hint">共 ${total} 条，当前显示 ${items.length} 条</p>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>时间</th>
                        <th>动作</th>
                        <th>操作人</th>
                        <th>单据</th>
                        <th>状态变更</th>
                        <th>原因</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${items.map(i => `
                        <tr>
                            <td>${this.formatDate(i.created_at)}</td>
                            <td><span class="badge">${this.escape(i.action)}</span></td>
                            <td>${this.escape(i.auditor_name)} (${i.auditor_role})</td>
                            <td><a href="#" onclick="App._viewDecisionChain(${i.bill_id}); return false;">#${i.bill_id}</a></td>
                            <td><code>${i.original_status || '?'} → ${i.new_status || '?'}</code></td>
                            <td><small>${this.escape((i.reason || '-').substring(0, 60))}</small></td>
                            <td>
                                <button class="btn-sm" onclick="App._viewAuditItemDetail(${JSON.stringify(i).replace(/"/g, '&quot;')})">详情</button>
                                ${i.ip_address ? `<button class="btn-sm" onclick="App._viewDecisionChain(${i.bill_id})">决策链</button>` : ''}
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    },

    _resetResearchAuditFilter() {
        document.getElementById('ra-action').value = '';
        document.getElementById('ra-from').value = '';
        document.getElementById('ra-to').value = '';
        this._applyResearchAuditFilter();
    },

    _viewAuditItemDetail(item) {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.id = 'audit-detail-modal';
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 600px;">
                <div class="modal-header">
                    <h3>审计详情</h3>
                    <button class="modal-close" onclick="document.getElementById('audit-detail-modal').remove()">×</button>
                </div>
                <div class="modal-body">
                    <table class="data-table">
                        <tr><th>ID</th><td>${item.id}</td></tr>
                        <tr><th>动作</th><td><code>${this.escape(item.action)}</code></td></tr>
                        <tr><th>操作人</th><td>${this.escape(item.auditor_name)} (${item.auditor_role}) #${item.auditor_id}</td></tr>
                        <tr><th>单据</th><td>#${item.bill_id}</td></tr>
                        <tr><th>状态变更</th><td><code>${item.original_status || '—'} → ${item.new_status || '—'}</code></td></tr>
                        <tr><th>原因</th><td>${this.escape(item.reason || '—')}</td></tr>
                        <tr><th>IP 地址</th><td><code>${item.ip_address || '—'}</code></td></tr>
                        <tr><th>客户端 ID</th><td><small>${item.client_id || '—'}</small></td></tr>
                        <tr><th>时间</th><td>${this.formatDate(item.created_at)}</td></tr>
                    </table>
                </div>
                <div class="modal-footer">
                    <button class="btn" onclick="document.getElementById('audit-detail-modal').remove()">关闭</button>
                    <button class="btn btn-primary" onclick="App._viewDecisionChain(${item.bill_id}); document.getElementById('audit-detail-modal').remove();">查看决策链</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        modal.addEventListener('click', (ev) => {
            if (ev.target === modal) modal.remove();
        });
    },

    // ============= 视图：应用升级向导（v2.4.0） =============
    async _view_upgrade(c) {
        c.innerHTML = `
            <div class="card">
                <h3>🚀 应用升级向导</h3>
                <p class="hint">从当前版本一键升级到最新版本。升级前会自动备份数据库，建议在业务低峰期操作。</p>
                <div id="up-current"></div>
                <div class="action-buttons">
                    <button class="btn btn-primary" onclick="App._upgradeCheck()">🔍 检查更新</button>
                    <button class="btn" onclick="App._upgradePrecheck()">⚙ 升级前预检</button>
                    <button class="btn" onclick="App._upgradeHistory()">📜 版本历史</button>
                </div>
            </div>
            <div id="up-content"></div>
        `;
        await this._upgradeRenderCurrent();
    },

    async _upgradeRenderCurrent() {
        const r = await this.api.get('/api/upgrade/current');
        const d = r.data || {};
        const el = document.getElementById('up-current');
        el.innerHTML = `
            <div class="version-display">
                <div class="version-box">
                    <label>当前版本</label>
                    <div class="version-num">${this.escape(d.current || '未知')}</div>
                </div>
                <div class="version-arrow">→</div>
                <div class="version-box">
                    <label>最新版本</label>
                    <div class="version-num">${this.escape(d.latest || '—')}</div>
                </div>
            </div>
        `;
    },

    async _upgradeCheck() {
        const el = document.getElementById('up-content');
        el.innerHTML = '<p class="placeholder">检查中...</p>';
        const r = await this.api.get('/api/upgrade/check');
        if (r.code !== 0) {
            el.innerHTML = '<p class="error">检查失败：' + r.message + '</p>';
            return;
        }
        const d = r.data;
        if (!d.has_update) {
            el.innerHTML = `
                <div class="card">
                    <h3 style="color: #27ae60;">✓ 已是最新版本</h3>
                    <p>当前 ${this.escape(d.current_version)} 与最新版本一致，无需升级。</p>
                </div>
            `;
            return;
        }
        const mandatory = d.mandatory_update
            ? '<span class="badge" style="background: #e74c3c; color: white; margin-left: 8px;">含强制升级</span>'
            : '';
        el.innerHTML = `
            <div class="card">
                <h3>📦 可升级版本（${d.pending_versions.length}）${mandatory}</h3>
                <p class="hint">从 <code>${this.escape(d.current_version)}</code> 升级到 <code>${this.escape(d.latest_version)}</code></p>
                <div id="up-pending-list">
                    ${d.pending_versions.map(v => this._renderPendingVersion(v)).join('')}
                </div>
                <div class="action-buttons" style="margin-top: 16px;">
                    <button class="btn btn-primary" onclick="App._upgradePrecheck()">下一步：升级前预检</button>
                </div>
            </div>
        `;
    },

    _renderPendingVersion(v) {
        const mandatoryTag = v.mandatory
            ? '<span class="badge" style="background: #e74c3c; color: white;">强制</span>'
            : '<span class="badge" style="background: #95a5a6; color: white;">可选</span>';
        return `
            <div class="version-item">
                <div>
                    <span class="version-num-small">${this.escape(v.version)}</span>
                    ${mandatoryTag}
                </div>
                <div style="flex: 1; margin-left: 12px;">
                    <strong>${this.escape(v.title)}</strong>
                    <small style="color: #7f8c8d; margin-left: 8px;">${this.escape(v.release_date || '')}</small>
                </div>
                <button class="btn-sm" onclick="App._upgradeShowChangelog('${v.version}')">查看</button>
            </div>
        `;
    },

    async _upgradeShowChangelog(version) {
        const r = await this.api.get(`/api/upgrade/changelog/${version}`);
        if (r.code !== 0) { alert('加载失败：' + r.message); return; }
        const d = r.data;
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.id = 'changelog-modal';
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 700px;">
                <div class="modal-header">
                    <h3>${this.escape(d.title)} - ${this.escape(d.version)}</h3>
                    <button class="modal-close" onclick="document.getElementById('changelog-modal').remove()">×</button>
                </div>
                <div class="modal-body">
                    <pre style="white-space: pre-wrap; font-family: -apple-system, sans-serif; line-height: 1.6;">${this.escape(d.changelog)}</pre>
                </div>
                <div class="modal-footer">
                    <button class="btn" onclick="document.getElementById('changelog-modal').remove()">关闭</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        modal.addEventListener('click', (ev) => {
            if (ev.target === modal) modal.remove();
        });
    },

    async _upgradePrecheck() {
        const el = document.getElementById('up-content');
        el.innerHTML = '<p class="placeholder">预检中...</p>';
        const r = await this.api.get('/api/upgrade/precheck');
        const d = r.data;
        const okColor = d.ok ? '#27ae60' : '#e74c3c';
        el.innerHTML = `
            <div class="card">
                <h3>⚙ 升级前预检 <span style="color: ${okColor};">${d.ok ? '✓ 全部通过' : '✗ 存在问题'}</span></h3>
                ${d.checks.map(c => this._renderPrecheck(c)).join('')}
                <div class="action-buttons" style="margin-top: 16px;">
                    ${d.ok ? '<button class="btn btn-primary" onclick="App._upgradePerform()">🚀 一键升级</button>' : '<button class="btn" disabled style="opacity: 0.5;">请先解决问题</button>'}
                </div>
            </div>
        `;
    },

    _renderPrecheck(c) {
        const icon = c.ok ? (c.level === 'warning' ? '⚠' : '✓') : '✗';
        const color = c.ok ? (c.level === 'warning' ? '#e67e22' : '#27ae60') : '#e74c3c';
        return `
            <div class="precheck-item">
                <span style="color: ${color}; font-weight: bold; font-size: 18px; width: 24px; display: inline-block;">${icon}</span>
                <strong>${this.escape(c.name)}</strong>
                <span style="margin-left: 8px; color: #555;">${this.escape(c.message)}</span>
                ${c.level === 'warning' ? '<span class="badge" style="background: #e67e22; color: white; margin-left: 8px;">警告</span>' : ''}
            </div>
        `;
    },

    async _upgradePerform() {
        if (!confirm('确认执行升级？\n\n• 升级前会自动备份数据库\n• 升级过程不可中断\n• 建议在业务低峰期操作')) {
            return;
        }
        const el = document.getElementById('up-content');
        el.innerHTML = '<p class="placeholder">⏳ 升级中，请稍候...</p>';
        const r = await this.api.post('/api/upgrade/perform', {});
        const d = r.data || {};
        if (r.code === 0) {
            const color = '#27ae60';
            el.innerHTML = `
                <div class="card" style="border-left: 4px solid ${color};">
                    <h3 style="color: ${color};">✓ 升级成功</h3>
                    <p><strong>从</strong> <code>${this.escape(d.from_version)}</code></p>
                    <p><strong>到</strong> <code>${this.escape(d.to_version)}</code></p>
                    ${d.backup_path ? `<p><strong>备份</strong> <code>${this.escape(d.backup_path)}</code></p>` : ''}
                    <h4>升级日志</h4>
                    <pre style="background: #f0f0f0; padding: 8px; border-radius: 4px;">${(d.log || []).map(l => this.escape(l)).join('\n')}</pre>
                    <p class="hint">建议重启客户端以应用所有更改。</p>
                    <button class="btn" onclick="App._view_upgrade(document.getElementById('content'))">返回升级页</button>
                </div>
            `;
            this._upgradeRenderCurrent();
        } else {
            el.innerHTML = `
                <div class="card" style="border-left: 4px solid #e74c3c;">
                    <h3 style="color: #e74c3c;">✗ 升级失败</h3>
                    <p>${this.escape(r.message)}</p>
                    <pre style="background: #fee; padding: 8px; border-radius: 4px;">${(d.log || []).map(l => this.escape(l)).join('\n')}</pre>
                    ${d.backup_path ? `<p class="hint">如需回滚，可使用备份：<code>${this.escape(d.backup_path)}</code></p>` : ''}
                    <button class="btn" onclick="App._upgradePrecheck()">重新预检</button>
                </div>
            `;
        }
    },

    async _upgradeHistory() {
        const el = document.getElementById('up-content');
        el.innerHTML = '<p class="placeholder">加载中...</p>';
        const r = await this.api.get('/api/upgrade/list');
        if (r.code !== 0) {
            el.innerHTML = '<p class="error">加载失败：' + r.message + '</p>';
            return;
        }
        const items = r.data || [];
        el.innerHTML = `
            <div class="card">
                <h3>📜 版本历史（${items.length}）</h3>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>版本</th>
                            <th>标题</th>
                            <th>发布日期</th>
                            <th>强制</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${items.map(v => `
                            <tr>
                                <td><strong>${this.escape(v.version)}</strong></td>
                                <td>${this.escape(v.title)}</td>
                                <td>${this.escape(v.release_date || '')}</td>
                                <td>${v.mandatory ? '<span class="badge" style="background: #e74c3c; color: white;">是</span>' : '<span class="badge" style="background: #95a5a6; color: white;">否</span>'}</td>
                                <td><button class="btn-sm" onclick="App._upgradeShowChangelog('${v.version}')">查看 changelog</button></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    },

    // ============= 视图：数据字典（v2.5.0） =============
    async _view_data_dict(c) {
        const statsR = await this.api.get('/api/data-dict/stats');
        const stats = statsR.data || {};
        const tablesR = await this.api.get('/api/data-dict/tables');
        const tables = tablesR.data || [];

        c.innerHTML = `
            <div class="card">
                <h3>📖 数据字典</h3>
                <p class="hint">每张表每列的含义 + 业务规则。共 <strong>${stats.table_count}</strong> 张表 / <strong>${stats.column_count}</strong> 个字段 / <strong>${stats.row_count}</strong> 条数据。</p>
                <div class="stat-grid">
                    <div class="stat-card">
                        <div class="stat-num">${stats.table_count}</div>
                        <div class="stat-label">表数</div>
                    </div>
                    <div class="stat-card stat-card-primary">
                        <div class="stat-num">${stats.column_count}</div>
                        <div class="stat-label">字段数</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-num">${stats.row_count}</div>
                        <div class="stat-label">数据行</div>
                    </div>
                </div>
            </div>
            <div class="card">
                <h3>📋 表列表</h3>
                <div id="dd-table-list"></div>
            </div>
        `;

        const listEl = document.getElementById('dd-table-list');
        listEl.innerHTML = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>表名</th>
                        <th>说明</th>
                        <th>字段数</th>
                        <th>主键</th>
                        <th>外键</th>
                        <th>行数</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${tables.map(t => `
                        <tr>
                            <td><code>${this.escape(t.name)}</code></td>
                            <td>${this.escape(t.description)}</td>
                            <td>${t.columns.length}</td>
                            <td>${t.primary_key.map(pk => `<code>${pk}</code>`).join(', ')}</td>
                            <td>${t.foreign_keys.length}</td>
                            <td>${t.name === 'schema_migration' ? '—' : `<span class="badge">${t.row_count || 0}</span>`}</td>
                            <td><button class="btn-sm" onclick="App._viewTableDetail('${t.name}')">详情</button></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    },

    async _viewTableDetail(name) {
        const r = await this.api.get(`/api/data-dict/tables/${name}`);
        if (r.code !== 0) { alert('加载失败：' + r.message); return; }
        const t = r.data;
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.id = 'table-detail-modal';
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 900px;">
                <div class="modal-header">
                    <h3>📋 <code>${this.escape(t.name)}</code></h3>
                    <button class="modal-close" onclick="document.getElementById('table-detail-modal').remove()">×</button>
                </div>
                <div class="modal-body">
                    <p style="background: #f8f9fa; padding: 8px 12px; border-radius: 4px; margin-bottom: 12px;">
                        <strong>说明：</strong>${this.escape(t.description)}
                    </p>
                    <h4>字段（${t.columns.length}）</h4>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>列名</th>
                                <th>类型</th>
                                <th>可空</th>
                                <th>默认值</th>
                                <th>说明</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${t.columns.map(c => `
                                <tr>
                                    <td><code>${this.escape(c.name)}</code>${t.primary_key.includes(c.name) ? ' <span class="badge" style="background: #f39c12; color: white; font-size: 10px;">PK</span>' : ''}</td>
                                    <td><small>${this.escape(c.type)}</small></td>
                                    <td>${c.nullable ? '✓' : '✗'}</td>
                                    <td><small>${c.default ? this.escape(c.default) : '—'}</small></td>
                                    <td>
                                        ${c.comment ? `<strong>${this.escape(c.comment)}</strong>` : ''}
                                        ${c.enum ? `<br/><small style="color: #7f8c8d;">${this.escape(c.enum)}</small>` : ''}
                                        ${c.rule ? `<br/><small style="color: #e67e22;">${this.escape(c.rule)}</small>` : ''}
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                    ${t.foreign_keys.length ? `
                        <h4 style="margin-top: 16px;">外键关联（${t.foreign_keys.length}）</h4>
                        <ul>
                            ${t.foreign_keys.map(fk => `<li><code>${fk.columns.join(', ')}</code> → <code>${fk.ref}</code></li>`).join('')}
                        </ul>
                    ` : ''}
                    ${t.indexes.length ? `
                        <h4 style="margin-top: 16px;">索引（${t.indexes.length}）</h4>
                        <ul>
                            ${t.indexes.map(i => `<li><code>${this.escape(i.name)}</code>（${i.columns.join(', ')}）${i.unique ? ' <span class="badge" style="background: #9b59b6; color: white; font-size: 10px;">UNIQUE</span>' : ''}</li>`).join('')}
                        </ul>
                    ` : ''}
                </div>
                <div class="modal-footer">
                    <button class="btn" onclick="document.getElementById('table-detail-modal').remove()">关闭</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        modal.addEventListener('click', (ev) => {
            if (ev.target === modal) modal.remove();
        });
    },

    // ============= 视图：数据导出（v2.6.0） =============
    async _view_data_export(c) {
        c.innerHTML = `
            <div class="card">
                <h3>📤 数据导出</h3>
                <p class="hint">把业务数据导出为 Excel 文件，支持筛选条件。导出的 Excel 可直接用于数据备份或在其他系统导入。</p>
            </div>

            <div class="card">
                <h3>👥 用户导出</h3>
                <div class="form-group">
                    <label>角色筛选</label>
                    <select id="de-user-role">
                        <option value="">全部</option>
                        <option value="finance">财务</option>
                        <option value="auditor">稽核员</option>
                        <option value="reimburser">报销人</option>
                    </select>
                </div>
                <a class="btn btn-primary" id="de-users-link" href="/api/data-export/users.xlsx" target="_blank">
                    📥 导出用户 Excel
                </a>
            </div>

            <div class="card">
                <h3>📂 项目导出</h3>
                <div class="form-group">
                    <label>状态筛选</label>
                    <select id="de-proj-status">
                        <option value="">全部</option>
                        <option value="active">进行中</option>
                        <option value="closed">已结束</option>
                    </select>
                </div>
                <a class="btn btn-primary" id="de-projects-link" href="/api/data-export/projects.xlsx" target="_blank">
                    📥 导出项目 Excel
                </a>
            </div>

            <div class="card">
                <h3>💰 报销标准导出</h3>
                <a class="btn btn-primary" href="/api/data-export/standards.xlsx" target="_blank">
                    📥 导出报销标准 Excel
                </a>
            </div>

            <div class="card">
                <h3>📋 报销单导出（带筛选）</h3>
                <div class="form-grid">
                    <div class="form-group">
                        <label>开始日期</label>
                        <input type="date" id="de-bill-start">
                    </div>
                    <div class="form-group">
                        <label>结束日期</label>
                        <input type="date" id="de-bill-end">
                    </div>
                    <div class="form-group">
                        <label>状态</label>
                        <select id="de-bill-status">
                            <option value="">全部</option>
                            <option value="archived">已归档</option>
                            <option value="approved">已批准</option>
                            <option value="rejected_finance">财务驳回</option>
                            <option value="rejected_auditor">稽核驳回</option>
                        </select>
                    </div>
                </div>
                <a class="btn btn-primary" id="de-bills-link" href="/api/data-export/bills.xlsx" target="_blank">
                    📥 导出报销单 Excel
                </a>
            </div>
        `;

        // 绑定筛选
        document.getElementById('de-user-role').onchange = () => {
            const r = document.getElementById('de-user-role').value;
            document.getElementById('de-users-link').href = r
                ? `/api/data-export/users.xlsx?role=${r}`
                : '/api/data-export/users.xlsx';
        };
        document.getElementById('de-proj-status').onchange = () => {
            const s = document.getElementById('de-proj-status').value;
            document.getElementById('de-projects-link').href = s
                ? `/api/data-export/projects.xlsx?status=${s}`
                : '/api/data-export/projects.xlsx';
        };
        const updateBillsLink = () => {
            const params = new URLSearchParams();
            const s = document.getElementById('de-bill-start').value;
            const e = document.getElementById('de-bill-end').value;
            const st = document.getElementById('de-bill-status').value;
            if (s) params.set('start_date', s);
            if (e) params.set('end_date', e);
            if (st) params.set('status', st);
            const qs = params.toString();
            document.getElementById('de-bills-link').href = qs
                ? `/api/data-export/bills.xlsx?${qs}`
                : '/api/data-export/bills.xlsx';
        };
        document.getElementById('de-bill-start').onchange = updateBillsLink;
        document.getElementById('de-bill-end').onchange = updateBillsLink;
        document.getElementById('de-bill-status').onchange = updateBillsLink;
    },

    // ============= 视图：可视化大屏（v2.6.0） =============
    async _view_dashboard_screen(c) {
        c.innerHTML = `
            <div class="card">
                <h3>📊 可视化大屏</h3>
                <p class="hint">实时业务数据仪表盘。数据来自当前数据库，无外部依赖（SVG 渲染）。</p>
                <div class="toolbar">
                    <label>年份：</label>
                    <select id="db-year" onchange="App._dashboardRefresh()">
                        <option value="">本年</option>
                        <option value="2026">2026</option>
                        <option value="2025">2025</option>
                    </select>
                    <button class="btn" onclick="App._dashboardRefresh()">🔄 刷新</button>
                </div>
                <div id="db-overview"></div>
            </div>
            <div id="db-charts" class="dashboard-grid"></div>
        `;
        await this._dashboardRefresh();
    },

    async _dashboardRefresh() {
        const year = document.getElementById('db-year').value;
        const qs = year ? `?year=${year}` : '';

        // 总览
        const ovR = await this.api.get('/api/dashboard/overview' + qs);
        const ov = ovR.data || {};
        document.getElementById('db-overview').innerHTML = `
            <div class="stat-grid">
                <div class="stat-card stat-card-primary">
                    <div class="stat-num">${ov.bill_count || 0}</div>
                    <div class="stat-label">单据总数</div>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, #27ae60 0%, #16a085 100%); color: white;">
                    <div class="stat-num" style="color: white;">${ov.archived || 0}</div>
                    <div class="stat-label" style="color: rgba(255,255,255,0.9);">已归档</div>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, #e67e22 0%, #d35400 100%); color: white;">
                    <div class="stat-num" style="color: white;">${ov.pending || 0}</div>
                    <div class="stat-label" style="color: rgba(255,255,255,0.9);">待处理</div>
                </div>
                <div class="stat-card">
                    <div class="stat-num">¥${this.formatMoney(ov.year_amount || 0)}</div>
                    <div class="stat-label">${ov.year} 年合计</div>
                </div>
                <div class="stat-card">
                    <div class="stat-num">¥${this.formatMoney(ov.total_amount || 0)}</div>
                    <div class="stat-label">累计总额</div>
                </div>
                <div class="stat-card">
                    <div class="stat-num">${ov.user_count || 0}</div>
                    <div class="stat-label">活跃用户</div>
                    <small style="opacity: 0.7;">财 ${ov.finance_count} / 稽 ${ov.auditor_count} / 报 ${ov.reimb_count}</small>
                </div>
                <div class="stat-card">
                    <div class="stat-num">${ov.project_count || 0}</div>
                    <div class="stat-label">进行中项目</div>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, #9b59b6 0%, #8e44ad 100%); color: white;">
                    <div class="stat-num" style="color: white;">${ov.unread_count || 0}</div>
                    <div class="stat-label" style="color: rgba(255,255,255,0.9);">未读通知</div>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, #34495e 0%, #2c3e50 100%); color: white;">
                    <div class="stat-num" style="color: white;">${ov.db_version || '?'}</div>
                    <div class="stat-label" style="color: rgba(255,255,255,0.9);">数据库版本</div>
                </div>
            </div>
        `;

        // 图表
        const chartR = await this.api.get('/api/dashboard/charts' + qs);
        const d = chartR.data || {};
        document.getElementById('db-charts').innerHTML = `
            <div class="card chart-card-full">
                <h3>${d.monthly_svg.includes('年度报销') ? '' : ''}月度趋势</h3>
                ${d.monthly_svg || ''}
            </div>
            <div class="card chart-card-full">
                <h3>月度单据数</h3>
                ${d.monthly_count_svg || ''}
            </div>
            <div class="card">
                <h3>项目 TOP</h3>
                ${d.project_svg || ''}
            </div>
            <div class="card">
                <h3>报销人 TOP</h3>
                ${d.user_svg || ''}
            </div>
            <div class="card">
                <h3>状态分布</h3>
                ${d.status_svg || ''}
            </div>
        `;
    },

    // ============= 视图：票据识别 OCR（v2.7.0） =============
    async _view_ocr(c) {
        c.innerHTML = `
            <div class="card">
                <h3>📷 票据识别</h3>
                <p class="hint">上传发票/车票/出租车票图片，自动识别金额、日期、票号等字段，生成报销单草稿。
                <br/>⚠ 当前使用 <strong>模拟 OCR 引擎</strong>，接入真实 OCR 服务后即可自动识别。
                沙箱无外网，<code>BAIDU_OCR_TOKEN</code> 等需部署时配置。</p>

                <div class="form-group">
                    <label>选择票据图片（jpg / png / pdf，最大 10MB）</label>
                    <input type="file" id="ocr-file" accept=".jpg,.jpeg,.png,.pdf,.bmp,.gif">
                </div>
                <div class="form-group">
                    <label>报销项目</label>
                    <select id="ocr-project">
                        <option value="">-- 加载中 --</option>
                    </select>
                </div>
                <button class="btn btn-primary" onclick="App._ocrUpload()">📤 上传并识别</button>
            </div>

            <div class="card" id="ocr-result" style="display: none;">
                <h3>识别结果</h3>
                <div id="ocr-fields"></div>
                <p class="hint" id="ocr-status"></p>
                <div class="action-buttons">
                    <button class="btn btn-primary" onclick="App._ocrCreateBill()">✓ 创建报销单草稿</button>
                </div>
            </div>

            <div class="card" id="ocr-history">
                <h3>📋 说明</h3>
                <p>当前支持的票据类型：</p>
                <ul>
                    <li>增值税发票（PDF/JPG）</li>
                    <li>火车票 / 机票行程单</li>
                    <li>出租车票 / 滴滴电子发票</li>
                    <li>酒店住宿发票</li>
                    <li>其他通用票据</li>
                </ul>
                <p class="hint">OCR 引擎接入后，识别准确率可达 95%+，字段自动填充。</p>
            </div>
        `;
        await this._ocrLoadProjects();
    },

    async _ocrLoadProjects() {
        const r = await this.api.get('/api/projects/list');
        const projs = (r.data || []).filter(p => p.status === 'active');
        const sel = document.getElementById('ocr-project');
        sel.innerHTML = '<option value="">-- 选择项目 --</option>' +
            projs.map(p => `<option value="${p.id}">${this.escape(p.project_name)} (${p.project_code})</option>`).join('');
    },

    async _ocrUpload() {
        const fileInput = document.getElementById('ocr-file');
        if (!fileInput.files[0]) {
            alert('请选择文件');
            return;
        }
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        const r = await fetch('/api/ocr/upload', {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
        });
        const result = await r.json();
        if (result.code !== 0) {
            alert('上传失败：' + result.message);
            return;
        }
        this._ocrData = result.data;
        document.getElementById('ocr-result').style.display = 'block';
        const fields = result.data.ocr.fields;
        document.getElementById('ocr-fields').innerHTML = `
            <div class="form-group">
                <label>票据类型</label>
                <input type="text" id="ocr-f-type" value="${this.escape(fields.receipt_type)}">
            </div>
            <div class="form-group">
                <label>发票号</label>
                <input type="text" id="ocr-f-no" value="${this.escape(fields.invoice_no)}">
            </div>
            <div class="form-group">
                <label>金额（元）</label>
                <input type="text" id="ocr-f-amount" value="${this.escape(fields.amount)}">
            </div>
            <div class="form-group">
                <label>日期</label>
                <input type="text" id="ocr-f-date" value="${this.escape(fields.date)}" placeholder="YYYY-MM-DD">
            </div>
            <div class="form-group">
                <label>销售方/抬头</label>
                <input type="text" id="ocr-f-vendor" value="${this.escape(fields.vendor)}">
            </div>
        `;
        document.getElementById('ocr-status').textContent = result.data.ocr.message;
    },

    async _ocrCreateBill() {
        const project_id = parseInt(document.getElementById('ocr-project').value);
        if (!project_id) { alert('请选择项目'); return; }
        const ocr_data = {
            fields: {
                receipt_type: document.getElementById('ocr-f-type').value,
                invoice_no: document.getElementById('ocr-f-no').value,
                amount: document.getElementById('ocr-f-amount').value,
                date: document.getElementById('ocr-f-date').value,
                vendor: document.getElementById('ocr-f-vendor').value,
            },
            status: this._ocrData.ocr.status,
        };
        const r = await this.api.post('/api/ocr/create-bill', {
            ocr_data,
            project_id,
            attachment_id: this._ocrData.attachment_id,
        });
        if (r.code !== 0) {
            alert('创建失败：' + r.message);
            return;
        }
        alert(r.message + '\n单据号：' + r.data.bill_no);
        this._view_my_bills(document.getElementById('content'));
    },

    // ============= 视图：调令识别 OCR（v2.8.0） =============
    async _view_transfer_ocr(c) {
        c.innerHTML = `
            <div class="card">
                <h3>📑 人员调令识别</h3>
                <p class="hint">上传借调 / 跟班学习 / 实战练兵 调令图片，自动识别<strong>真实姓名</strong>与<strong>有效期时段</strong>，并支持人工修正与绑定系统用户。
                <br/>⚠ 当前使用<strong>模拟 OCR 引擎</strong>，真实引擎接入后字段自动填充。</p>

                <div class="form-group">
                    <label>选择调令图片（jpg / png / pdf，最大 10MB）</label>
                    <input type="file" id="tocr-file" accept=".jpg,.jpeg,.png,.pdf,.bmp,.gif">
                </div>
                <button class="btn btn-primary" onclick="App._tocrUpload()">📤 上传并识别</button>
            </div>

            <div class="card" id="tocr-result" style="display: none;">
                <h3>识别结果</h3>
                <p class="hint" id="tocr-status"></p>
                <div id="tocr-fields"></div>
                <div class="action-buttons">
                    <button class="btn btn-primary" onclick="App._tocrSave()">✓ 保存调令</button>
                </div>
            </div>

            <div class="card" id="tocr-list-card">
                <h3>📋 已录入调令（最近 20）</h3>
                <div id="tocr-list"></div>
            </div>
        `;
        await this._tocrList();
    },

    async _tocrUpload() {
        const fileInput = document.getElementById('tocr-file');
        if (!fileInput.files[0]) {
            alert('请选择文件');
            return;
        }
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        const r = await fetch('/api/ocr/transfer/upload', {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
        });
        const result = await r.json();
        if (result.code !== 0) {
            alert('上传失败：' + result.message);
            return;
        }
        this._tocrData = result.data;
        document.getElementById('tocr-result').style.display = 'block';
        document.getElementById('tocr-status').textContent = result.data.ocr.message;
        const f = result.data.ocr.fields;
        document.getElementById('tocr-fields').innerHTML = `
            <div class="form-group">
                <label>调令类型 <span style="color: var(--danger);">*</span></label>
                <select id="tocr-f-type">
                    <option value="borrow" ${f.transfer_type === 'borrow' ? 'selected' : ''}>借调</option>
                    <option value="follow_training" ${f.transfer_type === 'follow_training' ? 'selected' : ''}>跟班学习</option>
                    <option value="combat_training" ${f.transfer_type === 'combat_training' ? 'selected' : ''}>实战练兵</option>
                    <option value="other" ${f.transfer_type === 'other' || !f.transfer_type ? 'selected' : ''}>其他</option>
                </select>
            </div>
            <div class="form-group">
                <label>真实姓名 <span style="color: var(--danger);">*</span></label>
                <input type="text" id="tocr-f-name" value="${this.escape(f.real_name)}" placeholder="如：张三">
            </div>
            <div class="form-group">
                <label>身份证号</label>
                <input type="text" id="tocr-f-idcard" value="${this.escape(f.id_card_no)}" placeholder="可选">
            </div>
            <div class="form-group">
                <label>调令编号（公文文号）</label>
                <input type="text" id="tocr-f-no" value="${this.escape(f.transfer_no)}">
            </div>
            <div style="display: flex; gap: 12px;">
                <div class="form-group" style="flex: 1;">
                    <label>原单位 / 派出单位</label>
                    <input type="text" id="tocr-f-source" value="${this.escape(f.source_unit)}">
                </div>
                <div class="form-group" style="flex: 1;">
                    <label>接收单位 / 我单位</label>
                    <input type="text" id="tocr-f-target" value="${this.escape(f.target_unit)}">
                </div>
            </div>
            <div class="form-group">
                <label>签发人 / 签发单位</label>
                <input type="text" id="tocr-f-issuer" value="${this.escape(f.issuer)}">
            </div>
            <div style="display: flex; gap: 12px;">
                <div class="form-group" style="flex: 1;">
                    <label>签发日期</label>
                    <input type="date" id="tocr-f-issue" value="${this.escape(f.issue_date)}">
                </div>
                <div class="form-group" style="flex: 1;">
                    <label>有效期起 <span style="color: var(--danger);">*</span></label>
                    <input type="date" id="tocr-f-start" value="${this.escape(f.start_date)}">
                </div>
                <div class="form-group" style="flex: 1;">
                    <label>有效期止 <span style="color: var(--danger);">*</span></label>
                    <input type="date" id="tocr-f-end" value="${this.escape(f.end_date)}">
                </div>
            </div>
            <div class="form-group">
                <label>备注</label>
                <textarea id="tocr-f-remark" rows="2" placeholder="可选"></textarea>
            </div>
        `;
    },

    async _tocrSave() {
        const fields = {
            transfer_type: document.getElementById('tocr-f-type').value,
            real_name: document.getElementById('tocr-f-name').value.trim(),
            id_card_no: document.getElementById('tocr-f-idcard').value.trim(),
            transfer_no: document.getElementById('tocr-f-no').value.trim(),
            source_unit: document.getElementById('tocr-f-source').value.trim(),
            target_unit: document.getElementById('tocr-f-target').value.trim(),
            issuer: document.getElementById('tocr-f-issuer').value.trim(),
            issue_date: document.getElementById('tocr-f-issue').value,
            start_date: document.getElementById('tocr-f-start').value,
            end_date: document.getElementById('tocr-f-end').value,
            remark: document.getElementById('tocr-f-remark').value.trim(),
            ocr_engine: 'manual',
        };
        if (!fields.real_name) { alert('请填真实姓名'); return; }
        if (!fields.start_date || !fields.end_date) { alert('请填有效期'); return; }
        const r = await this.api.post('/api/ocr/transfer/save', {
            fields,
            attachment_id: this._tocrData.attachment_id,
        });
        if (r.code !== 0) {
            alert('保存失败：' + r.message);
            return;
        }
        alert('已保存：' + r.message);
        document.getElementById('tocr-result').style.display = 'none';
        document.getElementById('tocr-file').value = '';
        await this._tocrList();
    },

    async _tocrList() {
        const r = await this.api.get('/api/ocr/transfer/list?page=1&page_size=20');
        if (r.code !== 0) { document.getElementById('tocr-list').innerHTML = '加载失败'; return; }
        const items = r.data.items || [];
        const typeMap = { borrow: '借调', follow_training: '跟班学习', combat_training: '实战练兵', other: '其他' };
        const statusMap = { active: '有效', expired: '已过期', cancelled: '已作废' };
        const html = items.length === 0
            ? '<p class="hint">暂无调令记录</p>'
            : `<table class="data-table">
                <thead><tr><th>ID</th><th>类型</th><th>真实姓名</th><th>有效期</th><th>原单位</th><th>状态</th><th>已绑定</th><th>录入人</th><th>操作</th></tr></thead>
                <tbody>${items.map(t => `
                    <tr>
                        <td>${t.id}</td>
                        <td>${typeMap[t.transfer_type] || t.transfer_type}</td>
                        <td><strong>${this.escape(t.real_name)}</strong></td>
                        <td>${t.start_date} → ${t.end_date}</td>
                        <td>${this.escape(t.source_unit || '—')}</td>
                        <td><span class="badge ${t.status === 'active' ? 'badge-success' : t.status === 'expired' ? 'badge-warning' : ''}">${statusMap[t.status] || t.status}</span></td>
                        <td>${t.matched_user_id ? '✓' : '—'}</td>
                        <td>#${t.operator_id}</td>
                        <td>
                            <button class="btn btn-sm" onclick="App._tocrDetail(${t.id})">详情</button>
                            <button class="btn btn-sm" onclick="App._tocrBind(${t.id}, '${this.escape(t.real_name)}')">绑定</button>
                        </td>
                    </tr>
                `).join('')}</tbody>
            </table>`;
        document.getElementById('tocr-list').innerHTML = html;
    },

    async _tocrDetail(id) {
        const r = await this.api.get(`/api/ocr/transfer/${id}`);
        if (r.code !== 0) { alert('加载失败：' + r.message); return; }
        const t = r.data;
        const typeMap = { borrow: '借调', follow_training: '跟班学习', combat_training: '实战练兵', other: '其他' };
        const statusMap = { active: '有效', expired: '已过期', cancelled: '已作废' };
        const dlg = document.createElement('div');
        dlg.className = 'modal';
        dlg.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:1000;';
        dlg.innerHTML = `<div style="background:white;border-radius:8px;width:600px;max-width:90vw;max-height:90vh;overflow:auto;">
            <div style="padding:14px 20px;border-bottom:1px solid #ddd;display:flex;justify-content:space-between;">
                <strong>📑 调令详情 #${t.id}</strong>
                <button onclick="this.closest('.modal').remove()" style="background:none;border:none;font-size:20px;cursor:pointer;">×</button>
            </div>
            <div style="padding:20px;">
                <table class="data-table">
                    <tr><td style="width:140px;"><strong>类型</strong></td><td>${typeMap[t.transfer_type] || t.transfer_type}</td></tr>
                    <tr><td><strong>真实姓名</strong></td><td><strong>${this.escape(t.real_name)}</strong></td></tr>
                    <tr><td><strong>身份证</strong></td><td>${t.id_card_no || '—'}</td></tr>
                    <tr><td><strong>调令编号</strong></td><td>${this.escape(t.transfer_no || '—')}</td></tr>
                    <tr><td><strong>原单位</strong></td><td>${this.escape(t.source_unit || '—')}</td></tr>
                    <tr><td><strong>接收单位</strong></td><td>${this.escape(t.target_unit || '—')}</td></tr>
                    <tr><td><strong>签发人</strong></td><td>${this.escape(t.issuer || '—')}</td></tr>
                    <tr><td><strong>签发日期</strong></td><td>${t.issue_date || '—'}</td></tr>
                    <tr><td><strong>有效期</strong></td><td>${t.start_date} → ${t.end_date}</td></tr>
                    <tr><td><strong>状态</strong></td><td><span class="badge ${t.status === 'active' ? 'badge-success' : 'badge-warning'}">${statusMap[t.status] || t.status}</span></td></tr>
                    <tr><td><strong>已绑定用户</strong></td><td>${t.matched_user ? t.matched_user.real_name + '（' + t.matched_user.username + '）' : '<em style="color:#999">未绑定</em>'}</td></tr>
                    <tr><td><strong>录入人</strong></td><td>${t.operator ? t.operator.real_name : '#' + t.operator_id}</td></tr>
                    <tr><td><strong>OCR 引擎</strong></td><td>${t.ocr_engine}（置信度 ${t.confidence}）</td></tr>
                    <tr><td><strong>创建时间</strong></td><td>${t.created_at || '—'}</td></tr>
                </table>
            </div>
            <div style="padding:12px 20px;border-top:1px solid #ddd;text-align:right;background:#fafafa;">
                <button class="btn" onclick="this.closest('.modal').remove()">关闭</button>
            </div>
        </div>`;
        document.body.appendChild(dlg);
    },

    async _tocrBind(id, name) {
        const q = prompt(`为调令绑定系统用户\n\n请输入姓名查询：`, name);
        if (!q) return;
        const r = await this.api.get(`/api/ocr/transfer/search-user?name=${encodeURIComponent(q)}`);
        if (r.code !== 0 || !r.data || r.data.length === 0) {
            alert('未找到匹配用户');
            return;
        }
        const u = r.data[0];
        if (!confirm(`找到用户：${u.real_name}（${u.username} / ${u.role}）\n\n确认绑定到此调令？`)) return;
        const r2 = await this.api.post(`/api/ocr/transfer/${id}/bind-user`, { user_id: u.id });
        if (r2.code !== 0) { alert('绑定失败：' + r2.message); return; }
        alert('✓ ' + r2.message);
        await this._tocrList();
    },

    // ============= 视图：修改密码 =============
    _view_change_password(c) {
        c.innerHTML = `
            <div class="card">
                <h3>修改密码</h3>
                <form onsubmit="return App.doChangePassword(event)">
                    <div class="form-group">
                        <label>原密码</label>
                        <input type="password" id="cp-old" required>
                    </div>
                    <div class="form-group">
                        <label>新密码</label>
                        <input type="password" id="cp-new" required>
                        <small>至少 10 位，建议包含大小写字母+数字+特殊字符</small>
                    </div>
                    <div class="form-group">
                        <label>确认新密码</label>
                        <input type="password" id="cp-confirm" required>
                    </div>
                    <div class="form-message" id="cp-message"></div>
                    <button type="submit" class="btn btn-primary">修改</button>
                </form>
            </div>
        `;
    },

    async doChangePassword(e) {
        e.preventDefault();
        const old_password = document.getElementById('cp-old').value;
        const new_password = document.getElementById('cp-new').value;
        const confirm = document.getElementById('cp-confirm').value;
        if (new_password !== confirm) {
            document.getElementById('cp-message').textContent = '两次输入不一致';
            document.getElementById('cp-message').className = 'form-message error';
            return false;
        }
        const r = await this.api.post('/api/auth/change-password', { old_password, new_password });
        document.getElementById('cp-message').textContent = r.message;
        document.getElementById('cp-message').className = 'form-message' + (r.code === 0 ? ' success' : ' error');
        if (r.code === 0) {
            document.getElementById('cp-old').value = '';
            document.getElementById('cp-new').value = '';
            document.getElementById('cp-confirm').value = '';
        }
        return false;
    },

    // ============= 视图：考勤 =============
    async _view_attendance(c) {
        const isAuditor = this.currentUser.role === 'auditor';
        let targetUserHtml = '';
        if (isAuditor) {
            // 稽核员：列出代理的报销员，可选代填
            const r = await this.api.get('/api/users/list?role=reimburser');
            const users = (r.data || []).map(u => `<option value="${u.id}">${this.escape(u.real_name)}（${this.escape(u.username)}）</option>`).join('');
            targetUserHtml = `
                <div class="form-group">
                    <label>代填对象（模式 C）</label>
                    <select id="att-target">
                        <option value="">-- 自己 --</option>
                        ${users}
                    </select>
                    <p class="hint">选择"代填对象"后，记录会写入该报销员账号（用于模式 C 全代填）</p>
                </div>
            `;
        }
        c.innerHTML = `
            <div class="card">
                <h3>考勤录入</h3>
                <form onsubmit="return App.doRecordAttendance(event)">
                    ${targetUserHtml}
                    <div class="form-group">
                        <label>日期</label>
                        <input type="date" id="att-date" required>
                    </div>
                    <div class="form-group">
                        <label>工作小时</label>
                        <input type="number" id="att-hours" step="0.5" min="0" max="24" value="8">
                    </div>
                    <div class="form-group">
                        <label>地点</label>
                        <input type="text" id="att-location" placeholder="如 北京/项目部">
                    </div>
                    <div class="form-group">
                        <label>是否驻场（夜班）</label>
                        <select id="att-overnight">
                            <option value="false">否</option>
                            <option value="true">是</option>
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary">录入</button>
                </form>
            </div>
            ${isAuditor ? `
            <div class="card">
                <h3>📋 模式 C 说明</h3>
                <p class="hint">作为稽核员，您可以为有代理关系的报销员代填考勤：</p>
                <ol style="line-height: 1.8; margin-left: 20px;">
                    <li>选择"代填对象"为该报销员</li>
                    <li>填写考勤信息</li>
                    <li>提交后会写入该报销员的考勤记录</li>
                </ol>
                <p class="hint">⚠ 模式 C：被代理的报销员无需登录客户端，状态由您代为管理。</p>
            </div>
            ` : ''}
        `;
    },

    async doRecordAttendance(e) {
        e.preventDefault();
        const data = {
            attendance_date: document.getElementById('att-date').value,
            work_hours: parseFloat(document.getElementById('att-hours').value),
            is_overnight: document.getElementById('att-overnight').value === 'true',
            location: document.getElementById('att-location').value,
        };
        // 稽核员代填模式
        const targetEl = document.getElementById('att-target');
        if (targetEl && targetEl.value) {
            const r = await this.api.post('/api/attendance/record-for/' + targetEl.value, data);
            alert(r.message);
        } else {
            const r = await this.api.post('/api/attendance/record', data);
            alert(r.message);
        }
        return false;
    },

    // ============= 视图：考勤审批（v2.10.0） =============
    async _view_attendance_pending(c) {
        c.innerHTML = '<p class="placeholder">加载中...</p>';
        const r = await this.api.get('/api/attendance/pending');
        if (r.code !== 0) { c.innerHTML = '<p class="error">加载失败：' + r.message + '</p>'; return; }
        const items = r.data || [];
        c.innerHTML = `
            <div class="card">
                <h3>✅ 考勤审批（${items.length}）</h3>
                <p class="hint">报销员自助录入的考勤，需您审批通过后才记入档案。稽核员代填的考勤已自动审核。</p>
                ${items.length === 0 ? '<p class="placeholder">暂无待审考勤</p>' : `
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>ID</th><th>报销员</th><th>日期</th><th>状态</th><th>备注</th><th>录入人</th><th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${await Promise.all(items.map(async it => {
                            // 查报销员姓名
                            let reimbName = '#' + it.user_id;
                            let operatorName = '#' + it.created_by;
                            try {
                                const u = await this.api.get('/api/users/' + it.user_id);
                                if (u.code === 0) reimbName = u.data.real_name;
                                const op = await this.api.get('/api/users/' + it.created_by);
                                if (op.code === 0) operatorName = op.data.real_name;
                            } catch (e) {}
                            return `<tr>
                                <td>${it.id}</td>
                                <td>${this.escape(reimbName)}</td>
                                <td>${it.attendance_date}</td>
                                <td>${it.status}</td>
                                <td><small>${this.escape(it.remark || '-')}</small></td>
                                <td>${this.escape(operatorName)}</td>
                                <td>
                                    <button class="btn btn-sm btn-success" onclick="App._auditAttendance(${it.id}, 'approved')">✓ 通过</button>
                                    <button class="btn btn-sm btn-danger" onclick="App._auditAttendance(${it.id}, 'rejected')">✗ 驳回</button>
                                </td>
                            </tr>`;
                        })).then(arr => arr.join(''))}
                    </tbody>
                </table>
                `}
            </div>
        `;
    },

    async _auditAttendance(id, decision) {
        const r = await this.api.post('/api/attendance/' + id + '/audit', { decision });
        alert(r.message);
        if (r.code === 0) this._view_attendance_pending(document.getElementById('content'));
    },

    // ============= 视图：我的资料 =============
    async _view_my_info(c) {
        const r = await this.api.get('/api/users/' + this.currentUser.user_id);
        if (r.code !== 0) {
            c.innerHTML = '<p>加载失败</p>';
            return;
        }
        const u = r.data;
        c.innerHTML = `
            <div class="card">
                <h3>我的资料</h3>
                <div class="info-grid">
                    <div><label>账号</label><span>${this.escape(u.username)}</span></div>
                    <div><label>姓名</label><span>${this.escape(u.real_name)}</span></div>
                    <div><label>角色</label><span>${u.role}</span></div>
                    <div><label>岗位</label><span>${this.escape(u.level_name || '-')}</span></div>
                    <div><label>部门</label><span>${this.escape(u.department || '-')}</span></div>
                    <div><label>有效起</label><span>${this.formatDate(u.valid_start_date)}</span></div>
                    <div><label>有效止</label><span>${this.formatDate(u.valid_end_date)}</span></div>
                </div>
            </div>
        `;
    },

    // ============= 视图：我的报销人（稽核员） =============
    async _view_reimbursers(c) {
        const r = await this.api.get('/api/users/list?role=reimburser');
        const users = r.data || [];
        c.innerHTML = `
            <div class="card">
                <h3>我的报销人</h3>
                ${users.length ? `
                    <table class="data-table">
                        <thead><tr><th>账号</th><th>姓名</th><th>部门</th><th>项目</th></tr></thead>
                        <tbody>
                            ${users.map(u => `<tr>
                                <td>${this.escape(u.username)}</td>
                                <td>${this.escape(u.real_name)}</td>
                                <td>${this.escape(u.department || '-')}</td>
                                <td>${(u.project_ids || []).join(', ') || '-'}</td>
                            </tr>`).join('')}
                        </tbody>
                    </table>
                ` : '<p class="placeholder">暂无报销人</p>'}
            </div>
        `;
    },

    // ============= 视图：数据包交换 =============
    async _view_packages(c) {
        const r = await this.api.get('/api/packages/list');
        const items = (r.data && r.data.items) || [];
        c.innerHTML = `
            <div class="card">
                <h3>数据包列表</h3>
                ${items.length ? `
                    <table class="data-table">
                        <thead><tr><th>包 ID</th><th>类型</th><th>状态</th><th>导入时间</th></tr></thead>
                        <tbody>
                            ${items.map(i => `<tr>
                                <td>${this.escape(i.package_id.substring(0, 8))}...</td>
                                <td>${this.escape(i.package_type)}</td>
                                <td>${i.import_status}</td>
                                <td>${this.formatDate(i.imported_at)}</td>
                            </tr>`).join('')}
                        </tbody>
                    </table>
                ` : '<p class="placeholder">暂无数据包</p>'}
            </div>
        `;
    },

    // ============= 视图：审计日志 =============
    async _view_audit_logs(c) {
        const [auditRes, finRes, errRes] = await Promise.all([
            this.api.get('/api/audit/list?per_page=30'),
            this.api.get('/api/audit/finance-logs?per_page=30'),
            this.api.get('/api/audit/errors?per_page=10'),
        ]);

        c.innerHTML = `
            <div class="card">
                <h3>操作审计日志</h3>
                <table class="data-table">
                    <thead><tr><th>时间</th><th>操作人</th><th>角色</th><th>动作</th><th>目标</th><th>详情</th><th>IP</th></tr></thead>
                    <tbody>
                        ${(auditRes.data && auditRes.data.items || []).map(l => `
                            <tr>
                                <td>${this.formatDate(l.created_at)}</td>
                                <td>${this.escape(l.actor_name)}</td>
                                <td>${l.actor_role}</td>
                                <td><code>${l.action}</code></td>
                                <td>${l.target_type || '-'}/${l.target_id || '-'}</td>
                                <td><small>${this.escape((l.detail || '').substring(0, 80))}</small></td>
                                <td>${l.ip_address || '-'}</td>
                            </tr>
                        `).join('') || '<tr><td colspan="7" class="placeholder">无日志</td></tr>'}
                    </tbody>
                </table>
            </div>
            <div class="card">
                <h3>财务终审独立日志</h3>
                <table class="data-table">
                    <thead><tr><th>时间</th><th>财务</th><th>动作</th><th>单据</th><th>金额</th><th>原始/新状态</th><th>双签</th></tr></thead>
                    <tbody>
                        ${(finRes.data && finRes.data.items || []).map(l => `
                            <tr>
                                <td>${this.formatDate(l.created_at)}</td>
                                <td>${l.finance_user_id}</td>
                                <td>${l.action}</td>
                                <td>#${l.bill_id}</td>
                                <td>¥${this.formatMoney(l.amount)}</td>
                                <td>${l.original_status} → ${l.new_status}</td>
                                <td>${l.dual_signer_id || '-'}</td>
                            </tr>
                        `).join('') || '<tr><td colspan="7" class="placeholder">无日志</td></tr>'}
                    </tbody>
                </table>
            </div>
            <div class="card">
                <h3>系统错误日志</h3>
                <table class="data-table">
                    <thead><tr><th>时间</th><th>类型</th><th>消息</th></tr></thead>
                    <tbody>
                        ${(errRes.data && errRes.data.items || []).map(l => `
                            <tr>
                                <td>${this.formatDate(l.created_at)}</td>
                                <td>${l.type}</td>
                                <td>${this.escape((l.message || '').substring(0, 80))}</td>
                            </tr>
                        `).join('') || '<tr><td colspan="3" class="placeholder">无错误</td></tr>'}
                    </tbody>
                </table>
            </div>
        `;
    },

    // ============= 视图：终审独立审计（D3 决策） =============
    async _view_research_audit(c) {
        // 顶部筛选
        c.innerHTML = `
            <div class="card">
                <h3>终审独立审计（D3 决策）</h3>
                <p class="hint">本视图展示所有终审独立审计记录，包括 final_approve / final_reject / override / archive。每条记录带操作人、IP、客户端 ID 三元组，可用于内部审计与外部合规检查。</p>
                <div class="form-row">
                    <label>单据 ID</label>
                    <input type="number" id="ra-bill-id" class="form-control" placeholder="可选，过滤指定单据">
                    <label>动作</label>
                    <select id="ra-action" class="form-control">
                        <option value="">全部</option>
                        <option value="final_approve">终审通过</option>
                        <option value="final_reject">终审驳回</option>
                        <option value="override">强制修改</option>
                        <option value="archive">归档</option>
                    </select>
                    <label>起始日期</label>
                    <input type="date" id="ra-start" class="form-control">
                    <label>结束日期</label>
                    <input type="date" id="ra-end" class="form-control">
                    <button class="btn btn-primary" id="ra-search">查询</button>
                    <button class="btn" id="ra-export-bill">导出当前单据 PDF</button>
                    <button class="btn" id="ra-export-bill-docx">导出当前单据 Word</button>
                </div>
            </div>
            <div id="ra-list"></div>
        `;

        const renderList = async () => {
            const billId = document.getElementById('ra-bill-id').value;
            const action = document.getElementById('ra-action').value;
            const start = document.getElementById('ra-start').value;
            const end = document.getElementById('ra-end').value;

            const params = new URLSearchParams();
            if (billId) params.set('bill_id', billId);
            if (action) params.set('action', action);
            if (start) params.set('start_date', start);
            if (end) params.set('end_date', end);

            const r = await this.api.get('/api/audit/research/list?' + params.toString());
            const items = r.data || [];

            const actionLabels = {
                'final_approve': '终审通过',
                'final_reject': '终审驳回',
                'override': '强制修改',
                'archive': '归档',
            };

            const html = `
                <div class="card">
                    <h3>审计记录（${items.length} 条）</h3>
                    ${items.length > 0 ? `
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>时间</th>
                                    <th>单据</th>
                                    <th>操作人</th>
                                    <th>角色</th>
                                    <th>动作</th>
                                    <th>状态变更</th>
                                    <th>IP</th>
                                    <th>原因</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${items.map(i => `
                                    <tr>
                                        <td>${this.formatDate(i.created_at)}</td>
                                        <td>#${i.bill_id}</td>
                                        <td>${this.escape(i.auditor_name || '-')}</td>
                                        <td>${i.auditor_role}</td>
                                        <td><span class="badge">${actionLabels[i.action] || i.action}</span></td>
                                        <td>${i.original_status || '-'} → ${i.new_status || '-'}</td>
                                        <td><code>${i.ip_address || '-'}</code></td>
                                        <td><small>${this.escape((i.reason || '-').substring(0, 60))}</small></td>
                                        <td>
                                            <button class="btn-sm" onclick="app._view_research_audit_chain(${i.bill_id})">链路</button>
                                            <a class="btn-sm" href="/api/audit/research/export/${i.bill_id}" target="_blank">PDF</a>
                                            <a class="btn-sm" href="/api/audit/research/export/${i.bill_id}?format=docx" target="_blank">Word</a>
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    ` : '<p class="placeholder">无审计记录</p>'}
                </div>
            `;
            document.getElementById('ra-list').innerHTML = html;
        };

        // 事件绑定
        document.getElementById('ra-search').onclick = renderList;
        document.getElementById('ra-export-bill').onclick = () => {
            const billId = document.getElementById('ra-bill-id').value;
            if (!billId) {
                alert('请先填写单据 ID');
                return;
            }
            window.open(`/api/audit/research/export/${billId}`, '_blank');
        };
        document.getElementById('ra-export-bill-docx').onclick = () => {
            const billId = document.getElementById('ra-bill-id').value;
            if (!billId) {
                alert('请先填写单据 ID');
                return;
            }
            window.open(`/api/audit/research/export/${billId}?format=docx`, '_blank');
        };

        await renderList();
    },

    async _view_research_audit_chain(billId) {
        // 弹出终审链路详情
        const r = await this.api.get(`/api/audit/research/bill/${billId}`);
        if (r.code !== 0) {
            alert('查询失败: ' + r.message);
            return;
        }
        const { history, chain } = r.data;
        const status = chain.ok ? '✓ 完整' : '✗ 异常';
        const statusClass = chain.ok ? 'ok' : 'error';

        const html = `
            <div class="modal-mask" onclick="this.remove()">
                <div class="modal" onclick="event.stopPropagation()" style="max-width:900px; max-height:80vh; overflow:auto;">
                    <div class="modal-header">
                        <h3>单据 #${billId} 终审独立审计链路</h3>
                        <button class="modal-close" onclick="this.closest('.modal-mask').remove()">×</button>
                    </div>
                    <div class="modal-body">
                        <div class="audit-chain-status ${statusClass}">
                            完整性：<strong>${status}</strong>
                            &nbsp;|&nbsp; 记录数：<strong>${chain.count}</strong>
                            &nbsp;|&nbsp; 最后动作：<strong>${chain.last_action || '-'}</strong>
                        </div>
                        ${chain.message ? `<p class="hint">${chain.message}</p>` : ''}
                        ${history.length > 0 ? `
                            <table class="data-table">
                                <thead><tr><th>#</th><th>时间</th><th>操作人</th><th>动作</th><th>状态变更</th><th>IP</th><th>原因</th></tr></thead>
                                <tbody>
                                    ${history.map((h, idx) => `
                                        <tr>
                                            <td>${idx + 1}</td>
                                            <td>${this.formatDate(h.created_at)}</td>
                                            <td>${this.escape(h.auditor_name || '-')}</td>
                                            <td>${h.action}</td>
                                            <td>${h.original_status || '-'} → ${h.new_status || '-'}</td>
                                            <td><code>${h.ip_address || '-'}</code></td>
                                            <td>${this.escape((h.reason || '-').substring(0, 80))}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : '<p class="placeholder">无记录</p>'}
                    </div>
                    <div class="modal-footer">
                        <a class="btn btn-primary" href="/api/audit/research/export/${billId}" target="_blank">导出 PDF 报告</a>
                        <a class="btn btn-primary" href="/api/audit/research/export/${billId}?format=docx" target="_blank">导出 Word 报告</a>
                        <button class="btn" onclick="this.closest('.modal-mask').remove()">关闭</button>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', html);
    },

    // ============= 视图：报销标准 =============
    async _view_standards(c) {
        const r = await this.api.get('/api/standards/list');
        const items = r.data || [];
        c.innerHTML = `
            <div class="toolbar">
                <button class="btn btn-primary" onclick="App.showCreateStandard()">+ 新增标准</button>
            </div>
            <div class="card">
                <h3>内置报销标准（${items.length} 条）</h3>
                ${items.length ? `
                    <table class="data-table">
                        <thead><tr><th>岗位</th><th>人员类型</th><th>补助类型</th><th>金额</th><th>项目特定</th><th>有效期</th></tr></thead>
                        <tbody>
                            ${items.map(s => `
                                <tr>
                                    <td>${this.escape(s.level_name)}</td>
                                    <td>${this.escape(s.staff_type)}</td>
                                    <td>${this.escape(s.subsidy_type)}</td>
                                    <td>¥${this.formatMoney(s.amount)}</td>
                                    <td>${s.project_id ? '#' + s.project_id : '全局'}</td>
                                    <td>${this.formatDate(s.valid_start)} ~ ${this.formatDate(s.valid_end) || '至今'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                ` : '<p class="placeholder">暂无标准</p>'}
            </div>
        `;
    },

    async showCreateStandard() {
        const posRes = await this.api.get('/api/users/positions');
        const positions = posRes.data || [];
        document.getElementById('view-content').innerHTML = `
            <div class="card">
                <h3>新增报销标准</h3>
                <form onsubmit="return App.doCreateStandard(event)">
                    <div class="form-group">
                        <label>岗位</label>
                        <select id="std-pos" required>
                            ${positions.map(p => `<option value="${p.id}">${this.escape(p.level_name)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>人员类型</label>
                        <select id="std-staff">
                            <option value="在编">在编</option>
                            <option value="借调">借调</option>
                            <option value="跟班">跟班</option>
                            <option value="实战练兵">实战练兵</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>补助类型</label>
                        <select id="std-type">
                            <option value="伙食">伙食</option>
                            <option value="住宿">住宿</option>
                            <option value="交通">交通</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>金额（元/天）</label>
                        <input type="number" id="std-amount" min="0" step="0.01" required>
                    </div>
                    <div class="action-buttons">
                        <button type="submit" class="btn btn-primary">保存</button>
                        <button type="button" class="btn" onclick="App.navigate('standards')">取消</button>
                    </div>
                </form>
            </div>
        `;
    },

    async doCreateStandard(e) {
        e.preventDefault();
        const data = {
            position_id: parseInt(document.getElementById('std-pos').value),
            staff_type: document.getElementById('std-staff').value,
            subsidy_type: document.getElementById('std-type').value,
            amount: parseFloat(document.getElementById('std-amount').value),
        };
        const r = await this.api.post('/api/standards/create', data);
        alert(r.message);
        if (r.code === 0) this.navigate('standards');
        return false;
    },

    // ============= 视图：统计报表 =============
    async _view_reports(c) {
        const year = new Date().getFullYear();

        // 顶部筛选 + 导出按钮
        c.innerHTML = `
            <div class="card">
                <div class="report-toolbar">
                    <h3>统计报表</h3>
                    <div class="export-buttons">
                        <a class="btn btn-primary" href="/api/reports/export/comprehensive.xlsx?year=${year}" target="_blank">
                            📊 导出综合报表
                        </a>
                        <a class="btn btn-primary" href="/api/reports/export/comprehensive.docx?year=${year}" target="_blank">
                            📝 综合报表 Word
                        </a>
                        <a class="btn" href="/api/reports/export/projects.xlsx" target="_blank">
                            📁 项目汇总
                        </a>
                        <a class="btn" href="/api/reports/export/users.xlsx" target="_blank">
                            👥 报销人汇总
                        </a>
                        <a class="btn" href="/api/reports/export/bills.xlsx" target="_blank">
                            📋 单据明细
                        </a>
                    </div>
                </div>
                <div class="form-row" style="margin-top: 12px;">
                    <label>统计年份</label>
                    <input type="number" id="report-year" class="form-control" value="${year}" min="2020" max="2099">
                    <label>起始日期</label>
                    <input type="date" id="report-start" class="form-control">
                    <label>结束日期</label>
                    <input type="date" id="report-end" class="form-control">
                    <button class="btn" id="report-refresh">刷新</button>
                </div>
            </div>
            <div id="report-content"></div>
        `;

        const render = async () => {
            const y = document.getElementById('report-year').value;
            const start = document.getElementById('report-start').value;
            const end = document.getElementById('report-end').value;
            const queryBase = `?year=${y}` +
                (start ? `&start=${start}` : '') +
                (end ? `&end=${end}` : '');
            const billsQuery = `?` +
                (start ? `start=${start}&` : '') +
                (end ? `end=${end}&` : '');

            const [proj, user, status, month] = await Promise.all([
                this.api.get('/api/reports/projects' + queryBase),
                this.api.get('/api/reports/users' + queryBase),
                this.api.get('/api/reports/status'),
                this.api.get('/api/reports/monthly?year=' + y),
            ]);

            const totalAmount = Object.values(status.data || {})
                .reduce((sum, v) => sum + (v.total_amount || 0), 0);
            const totalCount = Object.values(status.data || {})
                .reduce((sum, v) => sum + (v.count || 0), 0);

            document.getElementById('report-content').innerHTML = `
                <div class="card">
                    <h3>总览</h3>
                    <div class="stat-grid">
                        <div class="stat-card stat-card-primary">
                            <div class="stat-num">${totalCount}</div>
                            <div class="stat-label">单据总数</div>
                        </div>
                        <div class="stat-card stat-card-primary">
                            <div class="stat-num">¥${this.formatMoney(totalAmount)}</div>
                            <div class="stat-label">报销总金额</div>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <h3>状态分布</h3>
                    <div class="stat-grid">
                        ${Object.entries(status.data || {}).map(([s, v]) => `
                            <div class="stat-card">
                                <div class="stat-num">${v.count}</div>
                                <div class="stat-label">${this._statusText(s)}</div>
                                <div class="stat-label">¥${this.formatMoney(v.total_amount)}</div>
                            </div>
                        `).join('') || '<p class="placeholder">无数据</p>'}
                    </div>
                </div>

                <div class="card">
                    <div class="report-section-header">
                        <h3>项目汇总</h3>
                        <a class="btn-sm" href="/api/reports/export/projects.xlsx${queryBase}" target="_blank">📥 Excel</a>
                        <a class="btn-sm" href="/api/reports/export/projects.pdf${queryBase ? queryBase.replace('?', '?').replace(/xlsx/g, 'pdf') : ''}" target="_blank">📄 PDF</a>
                        <a class="btn-sm" href="/api/reports/export/projects.docx${queryBase}" target="_blank">📝 Word</a>
                    </div>
                    ${(proj.data || []).length ? `
                        <table class="data-table">
                            <thead><tr><th>项目代码</th><th>项目名称</th><th>单据数</th><th>总金额</th></tr></thead>
                            <tbody>
                                ${proj.data.map(p => `
                                    <tr>
                                        <td>${this.escape(p.project_code)}</td>
                                        <td>${this.escape(p.project_name)}</td>
                                        <td>${p.bill_count}</td>
                                        <td><strong>¥${this.formatMoney(p.total_amount)}</strong></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    ` : '<p class="placeholder">暂无数据</p>'}
                </div>

                <div class="card">
                    <div class="report-section-header">
                        <h3>报销人汇总 TOP 10</h3>
                        <a class="btn-sm" href="/api/reports/export/users.xlsx${queryBase}" target="_blank">📥 Excel</a>
                        <a class="btn-sm" href="/api/reports/export/users.pdf${queryBase ? queryBase.replace(/xlsx/g, 'pdf') : ''}" target="_blank">📄 PDF</a>
                        <a class="btn-sm" href="/api/reports/export/users.docx${queryBase}" target="_blank">📝 Word</a>
                    </div>
                    ${(user.data || []).slice(0, 10).length ? `
                        <table class="data-table">
                            <thead><tr><th>姓名</th><th>部门</th><th>单据数</th><th>总金额</th></tr></thead>
                            <tbody>
                                ${user.data.slice(0, 10).map(u => `
                                    <tr>
                                        <td>${this.escape(u.real_name)}</td>
                                        <td>${this.escape(u.department)}</td>
                                        <td>${u.bill_count}</td>
                                        <td><strong>¥${this.formatMoney(u.total_amount)}</strong></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    ` : '<p class="placeholder">暂无数据</p>'}
                </div>

                <div class="card">
                    <div class="report-section-header">
                        <h3>${y} 年月度趋势</h3>
                        <a class="btn-sm" href="/api/reports/export/monthly.xlsx?year=${y}" target="_blank">📥 Excel</a>
                        <a class="btn-sm" href="/api/reports/export/monthly.docx?year=${y}" target="_blank">📝 Word</a>
                    </div>
                    ${(month.data || []).length ? `
                        <table class="data-table">
                            <thead><tr><th>月份</th><th>单据数</th><th>总金额</th></tr></thead>
                            <tbody>
                                ${month.data.map(m => `
                                    <tr>
                                        <td>${m.month}</td>
                                        <td>${m.bill_count}</td>
                                        <td>¥${this.formatMoney(m.total_amount)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    ` : '<p class="placeholder">暂无数据</p>'}
                </div>

                <div class="card">
                    <div class="report-section-header">
                        <h3>单据明细导出</h3>
                    </div>
                    <p class="hint">单据明细通常数据量大，建议按时间范围分批导出。导出的 Excel 含 11 列：单据编号 / 报销人 / 部门 / 项目 / 出差起止 / 目的地 / 金额 / 大写 / 状态 / 创建时间。</p>
                    <a class="btn btn-primary" href="/api/reports/export/bills.xlsx${billsQuery}" target="_blank">
                        📥 导出 Excel
                    </a>
                    <a class="btn" href="/api/reports/export/bills.pdf${billsQuery.replace(/xlsx/g, 'pdf')}" target="_blank">
                        📄 导出 PDF
                    </a>
                    <a class="btn" href="/api/reports/export/bills.docx${billsQuery}" target="_blank">
                        📝 导出 Word
                    </a>
                </div>
            `;
        };

        document.getElementById('report-refresh').onclick = render;
        await render();
    },

    // ============= 视图：代填报销（稽核员） =============
    async _view_agent_fill(c) {
        const usersRes = await this.api.get('/api/users/list?role=reimburser');
        const projectsRes = await this.api.get('/api/projects/list');
        const users = usersRes.data || [];
        const projects = projectsRes.data || [];

        c.innerHTML = `
            <div class="card">
                <h3>代填报销</h3>
                <p style="color: #999; font-size: 13px; margin-bottom: 16px;">
                    提示：代填的报销单提交后跳过稽核员初审直接到财务（G2 决策）
                </p>
                <form onsubmit="return App.doAgentFill(event)">
                    <div class="form-group">
                        <label>报销人</label>
                        <select id="af-user" required>
                            ${users.map(u => `<option value="${u.id}">${this.escape(u.real_name)} (${this.escape(u.username)})</option>`).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>项目</label>
                        <select id="af-proj" required>
                            ${projects.map(p => `<option value="${p.id}">${this.escape(p.project_code)} - ${this.escape(p.project_name)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>出发日期</label>
                        <input type="date" id="af-start" required>
                    </div>
                    <div class="form-group">
                        <label>返回日期</label>
                        <input type="date" id="af-end" required>
                    </div>
                    <div class="form-group">
                        <label>目的地</label>
                        <input type="text" id="af-dest" required>
                    </div>
                    <div class="form-group">
                        <label>交通费</label>
                        <input type="number" id="af-transport" value="0" min="0" step="0.01">
                    </div>
                    <div class="form-group">
                        <label>住宿费</label>
                        <input type="number" id="af-accom" value="0" min="0" step="0.01">
                    </div>
                    <div class="form-group">
                        <label>其他费</label>
                        <input type="number" id="af-other" value="0" min="0" step="0.01">
                    </div>
                    <div class="action-buttons">
                        <button type="submit" class="btn btn-primary">代填并提交</button>
                    </div>
                </form>
            </div>
        `;
    },

    async doAgentFill(e) {
        e.preventDefault();
        const data = {
            user_id: parseInt(document.getElementById('af-user').value),
            project_id: parseInt(document.getElementById('af-proj').value),
            bill_type: 'personal',
            travel_start_date: document.getElementById('af-start').value,
            travel_end_date: document.getElementById('af-end').value,
            destination: document.getElementById('af-dest').value,
            transport_fee: parseFloat(document.getElementById('af-transport').value) || 0,
            accommodation_fee: parseFloat(document.getElementById('af-accom').value) || 0,
            other_fee: parseFloat(document.getElementById('af-other').value) || 0,
        };

        const r = await this.api.post('/api/bills/create', data);
        if (r.code === 0) {
            const sub = await this.api.post(`/api/bills/${r.data.id}/submit`);
            alert(`代填成功！单号：${r.data.bill_no}\n${sub.message}`);
            this.navigate('all-bills');
        } else {
            alert(r.message);
        }
        return false;
    },

    // ============= 视图：中心节点同步 =============
    async _view_sync(c) {
        const statusRes = await this.api.get('/api/sync/status');
        const st = statusRes.data || {};

        c.innerHTML = `
            <div class="card">
                <h3>中心节点同步状态</h3>
                <div class="info-grid">
                    <div><label>运行模式</label><span>${st.offline_mode ? '🔒 离线模式' : '🌐 联网模式'}</span></div>
                    <div><label>中心节点</label><span>${st.center_node}</span></div>
                    <div><label>当前在线</label><span>${st.online ? '✅ 是' : '❌ 否'}</span></div>
                </div>
                <div class="action-buttons">
                    <button class="btn btn-primary" onclick="App.doPing()">🔄 心跳检测</button>
                    <button class="btn" onclick="App.navigate('sync')">刷新</button>
                </div>
                <div id="ping-result" class="form-message" style="margin-top: 16px;"></div>
            </div>
            <div class="card">
                <h3>说明</h3>
                <ul style="line-height: 2; color: #666;">
                    <li><strong>离线模式（默认）</strong>：所有数据本地存储，通过 .rbag 文件进行数据摆渡</li>
                    <li><strong>联网模式</strong>：与中心节点自动同步（需设置环境变量 <code>OFFLINE_MODE=false</code>）</li>
                    <li><strong>中心节点地址</strong>：通过环境变量 <code>CENTER_NODE_HOST</code> / <code>CENTER_NODE_PORT</code> 配置</li>
                    <li><strong>协议</strong>：HTTPS (TLS 1.2+)</li>
                </ul>
            </div>
        `;
    },

    async doPing() {
        const el = document.getElementById('ping-result');
        el.textContent = '正在检测...';
        el.className = 'form-message';
        const r = await this.api.get('/api/sync/ping');
        el.textContent = (r.data.ok ? '✅ ' : '❌ ') + r.message;
        el.className = 'form-message ' + (r.data.ok ? 'success' : 'error');
    },
};

// 启动
document.addEventListener('DOMContentLoaded', () => {
    App.checkSession();
});

// 暴露给 onclick
window.App = App;
