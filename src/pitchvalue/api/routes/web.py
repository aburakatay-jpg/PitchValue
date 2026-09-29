"""External web resources."""

import pathlib

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["web"])


def _get_markdown_html(title: str, filepath: str) -> str:
    path = pathlib.Path(filepath)
    content = path.read_text(encoding="utf-8") if path.exists() else "Content not found."
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PitchValue - {title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 800px;
            margin: 40px auto;
            padding: 20px;
            line-height: 1.6;
            color: #333;
        }}
        pre {{ white-space: pre-wrap; font-family: inherit; }}
    </style>
</head>
<body>
    <h1>PitchValue</h1>
    <pre>{content}</pre>
</body>
</html>"""


@router.get("/privacy", response_class=HTMLResponse)
def privacy_page() -> str:
    return _get_markdown_html("Privacy Policy", "PRIVACY_POLICY.md")


@router.get("/terms", response_class=HTMLResponse)
def terms_page() -> str:
    return _get_markdown_html("Terms of Service", "TERMS_OF_SERVICE.md")


@router.get("/account/delete", response_class=HTMLResponse)
def delete_account_page() -> str:
    """Provide the public web resource for account deletion."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Delete PitchValue Account</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 500px; margin: 40px auto; padding: 20px; line-height: 1.6; color: #333; 
        }
        h1 { font-size: 24px; margin-bottom: 24px; }
        h2 { font-size: 20px; margin-bottom: 16px; }
        .card { 
            background: #f9f9f9; padding: 24px; border-radius: 8px; 
            border: 1px solid #ddd; margin-bottom: 24px; 
        }
        .warning { color: #d93025; font-weight: bold; }
        label { display: block; margin-bottom: 8px; font-weight: 500; }
        input { 
            width: 100%; padding: 10px; margin-bottom: 16px; border: 1px solid #ccc; 
            border-radius: 4px; box-sizing: border-box; 
        }
        button { 
            background: #000; color: #fff; padding: 12px 20px; border: none; 
            border-radius: 4px; cursor: pointer; font-size: 16px; font-weight: 500; width: 100%; 
        }
        button.destructive { background: #d93025; }
        button:disabled { background: #ccc; cursor: not-allowed; }
        .hidden { display: none; }
        .error { color: #d93025; margin-bottom: 16px; }
    </style>
</head>
<body>
    <h1>PitchValue Account Deletion</h1>
    
    <div id="login-section" class="card">
        <h2>Sign In</h2>
        <p>You must sign in to initiate account deletion.</p>
        <div id="login-error" class="error hidden"></div>
        <form id="login-form">
            <label for="email">Email</label>
            <input type="email" id="email" required>
            <label for="password">Password</label>
            <input type="password" id="password" required>
            <button type="submit" id="login-button">Sign In</button>
        </form>
    </div>

    <div id="deletion-section" class="card hidden">
        <h2>Delete Account</h2>
        <p class="warning">
            Deleting your account is permanent. It will remove your profile, 
            preferences, My Bets, and all saved selections.
        </p>
        <p>
            <strong>Active Subscription:</strong> Deleting the PitchValue account 
            does not automatically cancel an App Store or Google Play subscription. 
            You must manage your billing separately in your device settings.
        </p>
        
        <div id="delete-error" class="error hidden"></div>
        
        <form id="delete-form">
            <p>Please enter your password again to confirm this destructive action.</p>
            <label for="confirm-password">Password Confirmation</label>
            <input type="password" id="confirm-password" required>
            <button type="submit" id="delete-button" class="destructive">
                Permanently Delete Account
            </button>
        </form>
    </div>

    <div id="success-section" class="card hidden">
        <h2>Account Deleted</h2>
        <p>Your PitchValue account has been successfully deleted.</p>
        <p>Provider revocation may still be processing. You can safely close this page.</p>
    </div>

    <script>
        let token = null;

        document.getElementById('login-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const errorEl = document.getElementById('login-error');
            const button = document.getElementById('login-button');
            errorEl.classList.add('hidden');
            button.disabled = true;

            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;

            try {
                const response = await fetch('/api/v1/auth/email/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password })
                });
                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.message || 'Login failed');
                }

                token = data.access_token;
                document.getElementById('login-section').classList.add('hidden');
                document.getElementById('deletion-section').classList.remove('hidden');
            } catch (err) {
                errorEl.textContent = err.message;
                errorEl.classList.remove('hidden');
            } finally {
                button.disabled = false;
            }
        });

        document.getElementById('delete-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const errorEl = document.getElementById('delete-error');
            const button = document.getElementById('delete-button');
            errorEl.classList.add('hidden');
            button.disabled = true;

            const password = document.getElementById('confirm-password').value;

            try {
                const response = await fetch('/api/v1/auth/account-deletion', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({ 
                        password_or_token: password,
                        provider_credential: null
                    })
                });
                
                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.message || 'Deletion failed');
                }

                document.getElementById('deletion-section').classList.add('hidden');
                document.getElementById('success-section').classList.remove('hidden');
            } catch (err) {
                errorEl.textContent = err.message;
                errorEl.classList.remove('hidden');
                button.disabled = false;
            }
        });
    </script>
</body>
</html>"""
