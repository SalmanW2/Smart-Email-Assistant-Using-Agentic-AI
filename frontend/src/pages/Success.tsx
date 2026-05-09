import { useSearchParams } from 'react-router-dom';

const Success = () => {
  const [searchParams] = useSearchParams();
  const msg = searchParams.get('msg') || 'Connection Successful!';
  const success = searchParams.get('success') !== 'false';
  const isAdminError = searchParams.get('is_admin_error') === 'true';

  const color = success ? 'green' : 'red';
  const icon = success ? '✅' : '❌';

  let actionButton;
  let descText;

  if (isAdminError) {
    actionButton = <a href="/admin/login" className="bg-red-600 text-white px-8 py-3 rounded-xl font-bold shadow-lg block hover:bg-red-700 transition-colors mb-3">Retry Admin Login</a>;
    descText = 'Please retry with an authorized administrator email address.';
  } else if (msg.includes('Session expired') || msg.includes('CSRF')) {
    actionButton = <a href="/" className="bg-slate-800 text-white px-8 py-3 rounded-xl font-bold shadow-lg block hover:bg-slate-900 transition-colors mb-3">Return to Home Page</a>;
    descText = 'Security timeout due to mode change or inactivity. Please start again.';
  } else {
    actionButton = <a href="https://t.me/Private_Mail_Assistent_Bot" className="bg-blue-600 text-white px-8 py-3 rounded-xl font-bold shadow-lg block hover:bg-blue-700 transition-colors mb-3">Open Telegram</a>;
    descText = 'You may now close this page and return to the bot.';
  }

  return (
    <div className="bg-slate-100 flex items-center justify-center min-h-screen font-sans p-4">
      <div className={`bg-white p-8 md:p-10 rounded-2xl shadow-xl text-center max-w-sm w-full border-b-8 border-${color}-500`}>
        <div className="text-5xl mb-6">{icon}</div>
        <h2 className="text-xl md:text-2xl font-bold text-slate-800 mb-2">{msg}</h2>
        <p className="text-sm md:text-base text-slate-500 mb-8">{descText}</p>
        {actionButton}
      </div>
    </div>
  );
};

export default Success;