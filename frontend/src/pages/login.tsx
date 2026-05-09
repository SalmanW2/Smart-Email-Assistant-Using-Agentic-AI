import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

const Login = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  useEffect(() => {
    if (!token) {
      // Block manual access
      alert('Invalid access. Please use the login link from Telegram.');
      return;
    }

    // Redirect to backend auth
    const backendUrl = (import.meta as any).env.VITE_API_URL || 'http://localhost:8000';
    window.location.href = `${backendUrl}/auth/login?token=${token}`;
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            Connecting to Gmail...
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Please complete the OAuth flow in the new window.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;