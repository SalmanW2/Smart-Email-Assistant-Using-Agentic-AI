from fastapi import APIRouter, Request, Form, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from database import (get_all_users, update_user_status, is_blocked, verify_admin_password, 
                      set_admin_password, get_admin_role, get_all_admins, add_new_admin, 
                      remove_admin, get_all_blocked, remove_blocked_record)
from auth import get_admin_login_url
import logging

frontend_router = APIRouter()
FAVICON_SVG = '<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>📧</text></svg>">'

# --- 1. Public Landing Page ---
@frontend_router.get("/", response_class=HTMLResponse)
async def landing_page():
    return f"""
    <html>
    <head>
        <title>Smart Email Assistant | Agentic AI</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        {FAVICON_SVG}
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Inter', sans-serif; scroll-behavior: smooth; }}
            .bg-grid {{ background-size: 40px 40px; background-image: linear-gradient(to right, rgba(0, 0, 0, 0.04) 1px, transparent 1px), linear-gradient(to bottom, rgba(0, 0, 0, 0.04) 1px, transparent 1px); }}
        </style>
    </head>
    <body class="bg-slate-50 text-slate-900 bg-grid relative overflow-x-hidden">

        <nav class="p-6 flex justify-between items-center max-w-7xl mx-auto">
            <div class="text-xl md:text-2xl font-extrabold text-blue-600 flex items-center gap-2 tracking-tight">
                <span>📧</span> 
                <span>Smart Email Assistant <span class="font-light text-slate-400 hidden md:inline ml-1">| Powered by Agentic AI</span></span>
            </div>
            <a href="/admin/login" class="text-slate-600 hover:text-blue-600 font-semibold transition-colors bg-white px-5 py-2 rounded-full shadow-sm border border-slate-200 text-sm md:text-base">Admin Login</a>
        </nav>

        <main class="flex flex-col items-center justify-center min-h-[75vh] text-center px-4 mt-4">
            <div class="inline-block bg-blue-100 text-blue-800 font-bold px-4 py-2 rounded-full mb-6 text-sm shadow-sm border border-blue-200">
                ✨ The Future of Email Management
            </div>
            <h1 class="text-5xl md:text-7xl font-extrabold tracking-tight mb-6 leading-tight text-slate-900">
                Your Inbox, Mastered by <br class="hidden md:block"><span class="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-purple-600">Agentic AI</span>
            </h1>
            <p class="text-xl text-slate-600 mb-10 max-w-2xl leading-relaxed">
                Stop drowning in emails. Get instant summaries, draft context-aware replies, and command your professional communication—all through a simple Telegram chat.
            </p>
            
            <div class="flex flex-col sm:flex-row gap-4 w-full sm:w-auto z-10">
                <a href="https://t.me/Private_Mail_Assistent_Bot" target="_blank" class="bg-blue-600 text-white px-10 py-4 rounded-2xl shadow-xl hover:bg-blue-700 hover:-translate-y-1 transition-all font-bold text-lg w-full sm:w-auto flex justify-center items-center gap-2">
                    Start on Telegram 🚀
                </a>
                <a href="#features" class="bg-white border border-slate-200 px-10 py-4 rounded-2xl shadow-sm hover:bg-slate-50 hover:-translate-y-1 transition-all font-bold text-lg text-slate-700 w-full sm:w-auto flex justify-center items-center">
                    See How It Works
                </a>
            </div>

            <div class="mt-12 flex flex-col md:flex-row items-center justify-center gap-3 text-sm text-slate-500 bg-white px-6 py-3 rounded-full border border-slate-200 shadow-sm">
                <div class="flex items-center gap-2">
                    <svg class="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8V7a4 4 0 00-8 0v4h8z"></path></svg>
                    <b>Bank-Level Security:</b>
                </div>
                <span>Secured by Official Google OAuth. We never store your passwords or emails.</span>
            </div>
        </main>

        <section id="features" class="py-24 bg-white border-t border-slate-200 relative">
            <div class="max-w-7xl mx-auto px-6">
                <div class="text-center mb-20">
                    <h2 class="text-4xl font-extrabold text-slate-900">Why Use Smart Email Assistant?</h2>
                    <p class="text-slate-500 mt-4 text-xl">Experience an inbox that practically manages itself.</p>
                </div>
                
                <div class="grid md:grid-cols-3 gap-8">
                    <div class="p-10 bg-gradient-to-br from-slate-50 to-white rounded-3xl border border-slate-100 shadow-lg hover:shadow-xl transition-all hover:-translate-y-2">
                        <div class="w-16 h-16 bg-blue-100 text-blue-600 rounded-2xl flex items-center justify-center text-3xl mb-6 shadow-inner">📝</div>
                        <h3 class="text-2xl font-bold text-slate-800 mb-4">Instant Summaries</h3>
                        <p class="text-slate-600 leading-relaxed">Skip the 20-message threads. Our Agentic AI reads the context and gives you the exact action points in bullet format.</p>
                    </div>
                    <div class="p-10 bg-gradient-to-br from-slate-50 to-white rounded-3xl border border-slate-100 shadow-lg hover:shadow-xl transition-all hover:-translate-y-2">
                        <div class="w-16 h-16 bg-purple-100 text-purple-600 rounded-2xl flex items-center justify-center text-3xl mb-6 shadow-inner">✍️</div>
                        <h3 class="text-2xl font-bold text-slate-800 mb-4">Smart Drafting</h3>
                        <p class="text-slate-600 leading-relaxed">Tell the bot "Tell John I'll finish the report by Friday." The AI will instantly generate a highly professional email ready to send.</p>
                    </div>
                    <div class="p-10 bg-gradient-to-br from-slate-50 to-white rounded-3xl border border-slate-100 shadow-lg hover:shadow-xl transition-all hover:-translate-y-2">
                        <div class="w-16 h-16 bg-green-100 text-green-600 rounded-2xl flex items-center justify-center text-3xl mb-6 shadow-inner">🔒</div>
                        <h3 class="text-2xl font-bold text-slate-800 mb-4">Absolute Privacy</h3>
                        <p class="text-slate-600 leading-relaxed">Your data remains yours. We use strict Google API standards to ensure your inbox remains completely encrypted and isolated.</p>
                    </div>
                </div>
            </div>
        </section>

        <footer class="bg-slate-900 text-white py-16 text-center">
            <h2 class="text-3xl font-bold mb-6">Ready to regain your time?</h2>
            <a href="https://t.me/Private_Mail_Assistent_Bot" target="_blank" class="inline-block bg-blue-600 hover:bg-blue-500 text-white px-10 py-4 rounded-full font-bold transition-all shadow-lg hover:shadow-xl hover:-translate-y-1">
                Link Your Inbox Now
            </a>
        </footer>
    </body>
    </html>
    """

# --- 2. Admin Login Page ---
@frontend_router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(error: str = "", msg: str = ""):
    alert_html = ""
    if error:
        alert_html = f'<div class="bg-red-100 text-red-700 p-3 rounded-lg mb-4 text-sm font-semibold">{error}</div>'
    elif msg:
        alert_html = f'<div class="bg-green-100 text-green-700 p-3 rounded-lg mb-4 text-sm font-semibold">{msg}</div>'

    return f"""
    <html>
    <head>
        <title>Admin Login - Smart Email Assistant</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        {FAVICON_SVG}
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-100 flex items-center justify-center min-h-screen font-sans p-4">
        <div class="bg-white p-8 md:p-10 rounded-2xl shadow-2xl w-full max-w-md">
            <div class="text-center mb-8">
                <h1 class="text-3xl font-bold text-slate-800">Admin Portal</h1>
                <p class="text-slate-500 mt-2 text-sm">Secure access for authorized personnel.</p>
            </div>
            
            {alert_html}

            <div class="text-center mb-6">
                <button onclick="window.location.href='/admin/auth/google'" class="w-full flex items-center justify-center gap-3 bg-white border border-slate-300 p-3 rounded-lg hover:bg-slate-50 transition-all shadow-sm">
                    <img src="https://www.google.com/favicon.ico" class="w-5 h-5">
                    <span class="font-semibold text-slate-700">Continue with Google</span>
                </button>
            </div>

            <div class="relative flex py-4 items-center">
                <div class="flex-grow border-t border-slate-200"></div>
                <span class="flex-shrink mx-4 text-slate-400 text-sm font-semibold">OR</span>
                <div class="flex-grow border-t border-slate-200"></div>
            </div>

            <div class="text-center mb-4">
                <p class="text-xs text-slate-500 mb-3 px-2">If you have configured a password, login below:</p>
            </div>
            <form action="/admin/login_with_password" method="POST" class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-slate-700 mb-1 text-left">Email Address</label>
                    <input type="email" name="email" required class="w-full p-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none">
                </div>
                <div>
                    <label class="block text-sm font-medium text-slate-700 mb-1 text-left">Password</label>
                    <input type="password" name="password" required class="w-full p-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none">
                </div>
                <button type="submit" class="w-full bg-slate-900 text-white p-3 rounded-lg font-bold hover:bg-slate-800 transition-all shadow-md">Login to Dashboard</button>
            </form>
        </div>
    </body>
    </html>
    """

@frontend_router.post("/admin/login_with_password")
async def login_with_password(response: Response, email: str = Form(...), password: str = Form(...)):
    if verify_admin_password(email, password):
        response = RedirectResponse(url="/admin/dashboard", status_code=302)
        response.set_cookie(key="admin_session", value=email, max_age=86400)
        return response
    else:
        return RedirectResponse(url="/admin/login?error=Invalid Email or Password", status_code=302)

@frontend_router.get("/admin/auth/google")
async def admin_auth_google():
    url = get_admin_login_url()
    return RedirectResponse(url=url)

# --- 3. Main Admin Dashboard ---
@frontend_router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    admin_email = request.cookies.get("admin_session")
    if not admin_email:
        return RedirectResponse(url="/admin/login")

    role = get_admin_role(admin_email)
    manage_admins_tab = ""
    if role == "super_admin":
        manage_admins_tab = f'<a href="#" onclick="showSection(\'manage-admins-section\', this)" class="nav-link block p-3 hover:bg-slate-800 text-slate-400 rounded-lg transition-all">Manage Admins</a>'

    users = get_all_users()
    users_html = ""
    for u in users:
        is_user_blocked = is_blocked("telegram", str(u['telegram_id']))
        
        if is_user_blocked:
            status_html = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-red-100 text-red-700">BLOCKED</span>'
            buttons_html = f'<button id="btn-unblock-{u["telegram_id"]}" onclick="unblockUser({u["telegram_id"]}, this.id)" class="bg-gray-100 text-gray-700 px-4 py-2 rounded-lg font-bold hover:bg-gray-200 transition-all text-sm whitespace-nowrap">Unblock</button>'
        elif u.get('is_verified'):
            status_html = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-green-100 text-green-700">APPROVED</span>'
            buttons_html = f'<button onclick="openBlockModal({u["telegram_id"]})" class="bg-red-50 text-red-600 px-4 py-2 rounded-lg font-bold hover:bg-red-600 hover:text-white transition-all text-sm whitespace-nowrap">Block</button>'
        else:
            status_html = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-yellow-100 text-yellow-700">PENDING</span>'
            buttons_html = f'''
                <button id="btn-app-{u["telegram_id"]}" onclick="approveUser({u['telegram_id']}, this.id)" class="bg-blue-50 text-blue-600 px-4 py-2 rounded-lg font-bold hover:bg-blue-600 hover:text-white transition-all text-sm whitespace-nowrap">Approve</button>
                <button onclick="openBlockModal({u['telegram_id']})" class="bg-red-50 text-red-600 px-4 py-2 rounded-lg font-bold hover:bg-red-600 hover:text-white transition-all text-sm whitespace-nowrap">Block</button>
            '''

        users_html += f'''
        <tr class="user-row border-b border-slate-100 hover:bg-slate-50 transition-all">
            <td class="p-4 min-w-[200px]">
                <div class="font-bold text-slate-800">{u.get('first_name', 'N/A')}</div>
                <div class="text-xs text-slate-400">ID: {u['telegram_id']} | @{u.get('username', 'none')}</div>
                <div class="text-sm text-blue-600 mt-1">{u.get('email', 'Email Not Linked')}</div>
            </td>
            <td class="p-4">{status_html}</td>
            <td class="p-4 text-sm text-slate-500 whitespace-nowrap">{u.get('created_at', '').split('T')[0]}</td>
            <td class="p-4 space-x-2 flex items-center">{buttons_html}</td>
        </tr>
        '''

    blocked_records = get_all_blocked()
    blocklist_html = ""
    for b in blocked_records:
        blocklist_html += f'''
        <tr class="border-b border-slate-100">
            <td class="p-4 font-semibold text-slate-800 whitespace-nowrap">{b['block_type'].upper()}: {b['block_value']}</td>
            <td class="p-4 text-slate-600 min-w-[150px]">{b.get('reason', 'No reason provided')}</td>
            <td class="p-4"><button onclick="requestRemoveBlock('{b['id']}')" class="text-blue-600 hover:underline font-semibold text-sm whitespace-nowrap">Remove Block</button></td>
        </tr>
        '''
    if not blocklist_html:
        blocklist_html = '<tr><td colspan="3" class="p-4 text-slate-500 text-center">No blocked records found.</td></tr>'

    admins = get_all_admins()
    admins_html = ""
    for a in admins:
        remove_btn = f'''<button onclick="requestRemoveAdmin('{a["id"]}')" class="text-red-600 hover:underline font-semibold text-sm whitespace-nowrap">Remove</button>''' if a['email'] != admin_email else '<span class="text-slate-400 text-sm font-bold whitespace-nowrap">Current User</span>'
        admins_html += f'''
        <tr class="border-b border-slate-100">
            <td class="p-4 font-semibold text-slate-800">{a['email']}</td>
            <td class="p-4 text-slate-600 capitalize">{a['role'].replace('_', ' ')}</td>
            <td class="p-4">{remove_btn}</td>
        </tr>
        '''

    return f"""
    <html>
    <head>
        <title>Dashboard - Smart Email Assistant</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        {FAVICON_SVG}
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            const SPINNER_SVG = `<svg class="animate-spin h-4 w-4 text-current inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>`;

            document.addEventListener("DOMContentLoaded", () => {{
                let activeTab = localStorage.getItem("activeAdminTab") || "users-section";
                let element = document.querySelector(`[onclick*="${{activeTab}}"]`);
                if (element) showSection(activeTab, element);
            }});

            function toggleMobileMenu() {{
                const sidebar = document.getElementById('sidebar');
                const overlay = document.getElementById('mobileOverlay');
                sidebar.classList.toggle('-translate-x-full');
                overlay.classList.toggle('hidden');
            }}

            function showSection(sectionId, element) {{
                localStorage.setItem("activeAdminTab", sectionId);
                
                document.querySelectorAll('.dashboard-section').forEach(el => el.classList.add('hidden'));
                document.getElementById(sectionId).classList.remove('hidden');
                
                document.querySelectorAll('.nav-link').forEach(el => {{
                    el.classList.remove('bg-blue-600', 'text-white', 'font-semibold');
                    el.classList.add('hover:bg-slate-800', 'text-slate-400');
                }});
                
                if(element) {{
                    element.classList.remove('hover:bg-slate-800', 'text-slate-400');
                    element.classList.add('bg-blue-600', 'text-white', 'font-semibold');
                }}

                if(window.innerWidth < 1024) {{
                    document.getElementById('sidebar').classList.add('-translate-x-full');
                    document.getElementById('mobileOverlay').classList.add('hidden');
                }}
            }}

            function filterUsers() {{
                let input = document.getElementById('searchInput').value.toLowerCase();
                let rows = document.querySelectorAll('.user-row');
                rows.forEach(row => {{
                    let text = row.innerText.toLowerCase();
                    row.style.display = text.includes(input) ? '' : 'none';
                }});
            }}

            function setButtonLoading(btnId) {{
                let btn = document.getElementById(btnId);
                if (btn) {{
                    btn.disabled = true;
                    btn.innerHTML = `${{SPINNER_SVG}} Processing...`;
                    btn.classList.add('opacity-75', 'cursor-not-allowed');
                }}
            }}

            let confirmActionCallback = null;

            function openAlert(title, message, isError = false) {{
                document.getElementById('alertTitle').innerText = title;
                document.getElementById('alertMessage').innerText = message;
                document.getElementById('alertTitle').className = isError ? 'text-xl font-bold text-red-600 mb-2' : 'text-xl font-bold text-green-600 mb-2';
                document.getElementById('alertModal').classList.remove('hidden');
            }}

            function closeAlert() {{
                document.getElementById('alertModal').classList.add('hidden');
            }}

            function openConfirmModal(title, message, callback) {{
                document.getElementById('confirmTitle').innerText = title;
                document.getElementById('confirmMessage').innerText = message;
                confirmActionCallback = callback;
                document.getElementById('customConfirmModal').classList.remove('hidden');
            }}

            function closeConfirmModal() {{
                document.getElementById('customConfirmModal').classList.add('hidden');
                confirmActionCallback = null;
            }}

            async function executeConfirm() {{
                setButtonLoading('btnConfirmAction');
                if (confirmActionCallback) await confirmActionCallback();
            }}

            let currentBlockId = null;

            function openBlockModal(tg_id) {{
                currentBlockId = tg_id;
                document.getElementById('blockModal').classList.remove('hidden');
            }}

            function closeBlockModal() {{
                currentBlockId = null;
                document.getElementById('blockReason').value = '';
                document.getElementById('blockModal').classList.add('hidden');
            }}

            async function submitBlock() {{
                let reason = document.getElementById('blockReason').value;
                if (!reason) {{ openAlert("Error", "Please provide a reason for blocking.", true); return; }}
                setButtonLoading('btnSubmitBlock');
                await fetch(`/admin/update/${{currentBlockId}}/blocked?reason=${{encodeURIComponent(reason)}}`, {{method: 'POST', credentials: 'same-origin'}});
                location.reload();
            }}

            async function approveUser(tg_id, btnId) {{
                setButtonLoading(btnId);
                await fetch(`/admin/update/${{tg_id}}/approved`, {{method: 'POST', credentials: 'same-origin'}});
                location.reload();
            }}

            async function unblockUser(tg_id, btnId) {{
                setButtonLoading(btnId);
                await fetch(`/admin/update/${{tg_id}}/pending`, {{method: 'POST', credentials: 'same-origin'}});
                location.reload();
            }}

            function requestRemoveBlock(recordId) {{
                openConfirmModal("Remove Block", "Are you sure you want to remove this block? The user will be returned to Pending status.", async () => {{
                    await fetch(`/admin/remove_block/${{recordId}}`, {{method: 'POST', credentials: 'same-origin'}});
                    location.reload();
                }});
            }}

            function requestRemoveAdmin(adminId) {{
                openConfirmModal("Remove Admin", "Are you sure you want to revoke this user's administrator privileges?", async () => {{
                    await fetch(`/admin/remove_admin/${{adminId}}`, {{method: 'POST', credentials: 'same-origin'}});
                    location.reload();
                }});
            }}

            async function submitNewAdmin(event) {{
                event.preventDefault();
                let email = document.getElementById('newAdminEmail').value;
                setButtonLoading('btnAddAdmin');
                
                let formData = new FormData();
                formData.append('email', email);
                formData.append('role', 'admin');
                
                try {{
                    let res = await fetch('/admin/add_admin', {{method: 'POST', body: formData, credentials: 'same-origin'}});
                    let data = await res.json();
                    if(data.status === 'ok') {{
                        location.reload();
                    }} else {{
                        openAlert("Error", data.message || "Failed to add administrator.", true);
                    }}
                }} catch (e) {{
                    openAlert("Error", "Network error occurred.", true);
                }} finally {{
                    let btn = document.getElementById('btnAddAdmin');
                    btn.innerHTML = 'Add Admin';
                    btn.disabled = false;
                    btn.classList.remove('opacity-75', 'cursor-not-allowed');
                }}
            }}

            // --- STRICT Password Logic (6-10 chars) ---
            async function handlePassSubmit(event) {{
                event.preventDefault(); 
                
                let step2 = document.getElementById('step2-div');
                let p1 = document.getElementById('newPass').value;
                let errDiv = document.getElementById('passErrorInline');
                let btn = document.getElementById('btnActionPass');

                if (step2.classList.contains('hidden')) {{
                    // Step 1: Validating New Password
                    if (p1.length < 6 || p1.length > 10) {{
                        errDiv.innerText = "Password must be between 6 and 10 characters long.";
                        errDiv.classList.remove('hidden');
                    }} else {{
                        errDiv.classList.add('hidden');
                        step2.classList.remove('hidden');
                        btn.innerText = "Save Password";
                        document.getElementById('confPass').required = true;
                        document.getElementById('confPass').focus();
                    }}
                }} else {{
                    // Step 2: Saving Password
                    let p2 = document.getElementById('confPass').value;
                    if(p1 !== p2) {{ 
                        errDiv.innerText = "Passwords do not match!"; 
                        errDiv.classList.remove('hidden'); 
                        return; 
                    }}
                    
                    errDiv.classList.add('hidden');
                    setButtonLoading('btnActionPass');
                    
                    let formData = new FormData();
                    formData.append('password', p1);
                    
                    try {{
                        let res = await fetch('/admin/set_password', {{
                            method: 'POST', 
                            body: formData, 
                            credentials: 'same-origin'
                        }});
                        
                        if (!res.ok) throw new Error("Server communication failed.");
                        
                        let data = await res.json();
                        
                        if(data.status === 'ok') {{ 
                            document.getElementById('passForm').reset();
                            step2.classList.add('hidden');
                            btn.innerHTML = 'Next';
                            btn.disabled = false;
                            btn.classList.remove('opacity-75', 'cursor-not-allowed');
                            document.getElementById('confPass').required = false;
                            
                            openAlert("Success", "Your new password has been saved securely.");
                        }} else {{
                            openAlert("Error", data.message || "Failed to save password.", true);
                        }}
                    }} catch (error) {{
                        openAlert("Error", "A network or database error occurred while saving.", true);
                    }} finally {{
                        if (btn.disabled) {{
                            btn.innerHTML = 'Save Password';
                            btn.disabled = false;
                            btn.classList.remove('opacity-75', 'cursor-not-allowed');
                        }}
                    }}
                }}
            }}
        </script>
    </head>
    <body class="bg-slate-50 min-h-screen font-sans">
        
        <div id="alertModal" class="hidden fixed inset-0 bg-slate-900 bg-opacity-50 flex items-center justify-center z-[60] p-4 transition-opacity">
            <div class="bg-white p-6 rounded-2xl shadow-2xl w-full max-w-sm text-center">
                <h3 id="alertTitle" class="text-xl font-bold mb-2"></h3>
                <p id="alertMessage" class="text-sm text-slate-600 mb-6"></p>
                <button onclick="closeAlert()" class="bg-slate-900 text-white px-6 py-2 rounded-lg font-bold hover:bg-slate-800 w-full">OK</button>
            </div>
        </div>

        <div id="customConfirmModal" class="hidden fixed inset-0 bg-slate-900 bg-opacity-50 flex items-center justify-center z-[60] p-4 transition-opacity">
            <div class="bg-white p-6 rounded-2xl shadow-2xl w-full max-w-sm text-center">
                <h3 id="confirmTitle" class="text-xl font-bold text-slate-800 mb-2">Confirm Action</h3>
                <p id="confirmMessage" class="text-sm text-slate-600 mb-6">Are you sure?</p>
                <div class="flex flex-col-reverse sm:flex-row justify-center gap-3">
                    <button onclick="closeConfirmModal()" class="px-4 py-2 rounded-lg font-semibold text-slate-600 hover:bg-slate-100 w-full sm:w-auto border border-slate-200">Cancel</button>
                    <button id="btnConfirmAction" onclick="executeConfirm()" class="px-4 py-2 bg-red-600 text-white rounded-lg font-semibold hover:bg-red-700 shadow-md w-full sm:w-auto">Confirm</button>
                </div>
            </div>
        </div>

        <div id="blockModal" class="hidden fixed inset-0 bg-slate-900 bg-opacity-50 flex items-center justify-center z-[60] p-4 transition-opacity">
            <div class="bg-white p-6 rounded-2xl shadow-2xl w-full max-w-md">
                <h3 class="text-xl font-bold text-slate-800 mb-2">Block User</h3>
                <p class="text-sm text-slate-500 mb-4">Please specify the reason for blocking this user.</p>
                <input type="text" id="blockReason" placeholder="e.g., Spamming..." class="w-full p-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-red-500 outline-none mb-6">
                <div class="flex flex-col-reverse sm:flex-row justify-end gap-3">
                    <button onclick="closeBlockModal()" class="px-4 py-2 rounded-lg font-semibold text-slate-600 hover:bg-slate-100 w-full sm:w-auto border border-slate-200 sm:border-0">Cancel</button>
                    <button id="btnSubmitBlock" onclick="submitBlock()" class="px-4 py-2 bg-red-600 text-white rounded-lg font-semibold hover:bg-red-700 shadow-md w-full sm:w-auto">Confirm Block</button>
                </div>
            </div>
        </div>

        <div class="lg:hidden bg-slate-900 text-white p-4 flex items-center justify-between sticky top-0 z-40 shadow-md">
            <button onclick="toggleMobileMenu()" class="p-2 bg-slate-800 rounded-lg focus:outline-none">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
            </button>
            <div class="text-lg font-bold flex items-center gap-2"><span>📧</span> Smart Email Assistant</div>
            <div class="w-10"></div> </div>

        <div id="mobileOverlay" onclick="toggleMobileMenu()" class="hidden fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"></div>

        <div class="flex">
            <div id="sidebar" class="fixed inset-y-0 left-0 transform -translate-x-full lg:relative lg:translate-x-0 transition duration-200 ease-in-out z-50 w-64 bg-slate-900 text-white min-h-screen p-6 overflow-y-auto shadow-2xl lg:shadow-none">
                <div class="text-xl font-bold mb-10 hidden lg:flex items-center gap-2"><span>📧</span> Smart Email Assistant</div>
                <div class="flex justify-between items-center lg:hidden mb-8">
                    <span class="text-xl font-bold text-slate-400">Admin Menu</span>
                    <button onclick="toggleMobileMenu()" class="text-slate-400 hover:text-white text-2xl font-bold">&times;</button>
                </div>
                
                <nav class="space-y-2">
                    <a href="#" onclick="showSection('users-section', this)" class="nav-link block p-3 bg-blue-600 text-white font-semibold rounded-lg transition-all">User Management</a>
                    <a href="#" onclick="showSection('blocklist-section', this)" class="nav-link block p-3 hover:bg-slate-800 text-slate-400 rounded-lg transition-all">Blocklist</a>
                    {manage_admins_tab}
                    <a href="#" onclick="showSection('set-password-section', this)" class="nav-link block p-3 hover:bg-slate-800 text-slate-400 rounded-lg transition-all">Set Password</a>
                    <div class="pt-8 border-t border-slate-800 mt-8">
                        <a href="/admin/logout" class="block p-3 text-red-400 hover:text-red-300 hover:bg-slate-800 rounded-lg transition-all">Logout</a>
                    </div>
                </nav>
            </div>

            <div class="flex-1 p-4 md:p-10 w-full overflow-hidden bg-slate-50 min-h-screen">
                
                <div id="users-section" class="dashboard-section hidden">
                    <div class="flex flex-col md:flex-row justify-between md:items-center mb-8 gap-4">
                        <h1 class="text-2xl md:text-3xl font-bold text-slate-800">User Management</h1>
                        <input type="text" id="searchInput" onkeyup="filterUsers()" placeholder="Search Users..." class="p-3 border border-slate-300 rounded-xl w-full md:w-80 shadow-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    </div>
                    
                    <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-x-auto">
                        <table class="w-full text-left min-w-[600px]">
                            <thead class="bg-slate-50 border-b border-slate-200">
                                <tr>
                                    <th class="p-4 text-sm font-semibold text-slate-600">Telegram User</th>
                                    <th class="p-4 text-sm font-semibold text-slate-600">Status</th>
                                    <th class="p-4 text-sm font-semibold text-slate-600">Registration Date</th>
                                    <th class="p-4 text-sm font-semibold text-slate-600">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {users_html}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div id="blocklist-section" class="dashboard-section hidden">
                    <h1 class="text-2xl md:text-3xl font-bold text-slate-800 mb-6">System Blocklist</h1>
                    <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-x-auto">
                        <table class="w-full text-left min-w-[500px]">
                            <thead class="bg-slate-50 border-b border-slate-200">
                                <tr>
                                    <th class="p-4 text-sm font-semibold text-slate-600">Target</th>
                                    <th class="p-4 text-sm font-semibold text-slate-600">Reason</th>
                                    <th class="p-4 text-sm font-semibold text-slate-600">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {blocklist_html}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div id="manage-admins-section" class="dashboard-section hidden">
                    <h1 class="text-2xl md:text-3xl font-bold text-slate-800 mb-6">Manage Administrators</h1>
                    
                    <div class="bg-white p-4 md:p-6 rounded-2xl shadow-sm border border-slate-200 mb-8">
                        <h2 class="text-lg font-bold text-slate-800 mb-4">Add New Admin</h2>
                        <form onsubmit="submitNewAdmin(event)" class="flex flex-col sm:flex-row gap-4 sm:items-end">
                            <div class="flex-1">
                                <label class="block text-sm font-medium text-slate-700 mb-1">Email Address</label>
                                <input type="email" id="newAdminEmail" required placeholder="newadmin@example.com" class="w-full p-3 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-blue-500">
                            </div>
                            <button type="submit" id="btnAddAdmin" class="bg-blue-600 text-white px-8 py-3 rounded-lg font-bold hover:bg-blue-700 h-[50px] shadow-sm w-full sm:w-auto transition-all">Add Admin</button>
                        </form>
                    </div>

                    <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-x-auto">
                        <table class="w-full text-left min-w-[400px]">
                            <thead class="bg-slate-50 border-b border-slate-200">
                                <tr>
                                    <th class="p-4 text-sm font-semibold text-slate-600">Email Address</th>
                                    <th class="p-4 text-sm font-semibold text-slate-600">Role</th>
                                    <th class="p-4 text-sm font-semibold text-slate-600">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {admins_html}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div id="set-password-section" class="dashboard-section hidden">
                    <h1 class="text-2xl md:text-3xl font-bold text-slate-800 mb-6">Set Admin Password</h1>
                    <div class="bg-white p-6 md:p-8 rounded-2xl shadow-sm border border-slate-200 max-w-lg">
                        <p class="text-slate-500 mb-6 text-sm md:text-base">Create a password to login directly without using Google SSO.</p>
                        
                        <form id="passForm" onsubmit="handlePassSubmit(event)" class="space-y-4">
                            <div>
                                <label class="block text-sm font-medium text-slate-700 mb-1">New Password</label>
                                <input type="password" id="newPass" required placeholder="6 to 10 characters" class="w-full p-3 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-blue-500">
                            </div>
                            
                            <div id="passErrorInline" class="text-red-500 text-sm font-semibold hidden"></div>

                            <div id="step2-div" class="hidden">
                                <label class="block text-sm font-medium text-slate-700 mb-1 mt-2">Confirm Password</label>
                                <input type="password" id="confPass" placeholder="Retype your password" class="w-full p-3 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-blue-500">
                            </div>
                            
                            <button type="submit" id="btnActionPass" class="bg-slate-800 text-white px-6 py-3 rounded-lg font-bold hover:bg-slate-900 shadow-md w-full transition-all">Next</button>
                        </form>
                    </div>
                </div>

            </div>
        </div>
    </body>
    </html>
    """

# --- 4. Success & Error Pages ---
@frontend_router.get("/callback_success", response_class=HTMLResponse)
async def success_page(msg: str, success: bool = True, is_admin_error: bool = False):
    color = "green" if success else "red"
    icon = "✅" if success else "❌"
    
    if is_admin_error:
        action_button = '<a href="/admin/login" class="bg-red-600 text-white px-8 py-3 rounded-xl font-bold shadow-lg block hover:bg-red-700 transition-colors mb-3">Retry Admin Login</a>'
        desc_text = "Please retry with an authorized administrator email address."
    elif "Session expired" in msg or "CSRF" in msg:
        action_button = '<a href="/" class="bg-slate-800 text-white px-8 py-3 rounded-xl font-bold shadow-lg block hover:bg-slate-900 transition-colors mb-3">Return to Home Page</a>'
        desc_text = "Security timeout due to mode change or inactivity. Please start again."
    else:
        action_button = '<a href="https://t.me/Private_Mail_Assistent_Bot" class="bg-blue-600 text-white px-8 py-3 rounded-xl font-bold shadow-lg block hover:bg-blue-700 transition-colors mb-3">Open Telegram</a>'
        desc_text = "You may now close this page and return to the bot."

    return f"""
    <html>
    <head>
        <title>Authentication Status</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        {FAVICON_SVG}
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-100 flex items-center justify-center min-h-screen font-sans p-4">
        <div class="bg-white p-8 md:p-10 rounded-2xl shadow-xl text-center max-w-sm w-full border-b-8 border-{color}-500">
            <div class="text-5xl mb-6">{icon}</div>
            <h2 class="text-xl md:text-2xl font-bold text-slate-800 mb-2">{msg}</h2>
            <p class="text-sm md:text-base text-slate-500 mb-8">{desc_text}</p>
            {action_button}
        </div>
    </body>
    </html>
    """

# --- 5. Admin API Routes ---
@frontend_router.post("/admin/update/{tg_id}/{status}")
async def change_status(tg_id: int, status: str, reason: str = ""):
    is_verified = True if status == "approved" else False
    update_user_status(tg_id, is_verified, status, reason)
    return {"status": "ok"}

@frontend_router.post("/admin/remove_block/{record_id}")
async def unblock_record(record_id: str):
    remove_blocked_record(record_id)
    return {"status": "ok"}

@frontend_router.post("/admin/set_password")
async def api_set_password(request: Request, password: str = Form(...)):
    admin_email = request.cookies.get("admin_session")
    if admin_email:
        try:
            set_admin_password(admin_email, password)
            return {"status": "ok"}
        except Exception as e:
            logging.error(f"Set Password Error: {e}")
            return {"status": "error", "message": f"Database Error: {str(e)}"}
    return {"status": "error", "message": "Cookie missing. Please log in again."}

@frontend_router.post("/admin/add_admin")
async def api_add_admin(request: Request, email: str = Form(...), role: str = Form(...)):
    admin_email = request.cookies.get("admin_session")
    if not admin_email:
        return {"status": "error", "message": "Authentication cookie missing. Please log in again."}
    try:
        if get_admin_role(admin_email) == "super_admin":
            add_new_admin(email, role, admin_email)
            return {"status": "ok"}
        return {"status": "error", "message": "You are not authorized as a Super Admin."}
    except Exception as e:
        return {"status": "error", "message": f"Database Error: {str(e)}"}

@frontend_router.post("/admin/remove_admin/{admin_id}")
async def api_remove_admin(request: Request, admin_id: str):
    admin_email = request.cookies.get("admin_session")
    if get_admin_role(admin_email) == "super_admin":
        remove_admin(admin_id)
        return {"status": "ok"}
    return Response(status_code=403)

@frontend_router.get("/admin/logout")
async def admin_logout(response: Response):
    response = RedirectResponse(url="/admin/login?msg=Logged out successfully")
    response.delete_cookie("admin_session")
    return response