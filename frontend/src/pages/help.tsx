import { useState, useEffect } from 'react';

interface Admin {
  name: string;
  email: string;
}

const Help = () => {
  const [admins, setAdmins] = useState<Admin[]>([]);

  useEffect(() => {
    loadAdmins();
  }, []);

  const loadAdmins = async () => {
    try {
      // const response = await api.getAdminUsers();
      setAdmins([
        { name: 'Admin One', email: 'admin1@example.com' },
        { name: 'Admin Two', email: 'admin2@example.com' }
      ]);
    } catch (error) {
      console.error('Failed to load admins');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <h1 className="text-xl font-semibold">Help & Guidelines</h1>
            </div>
            <div className="flex items-center">
              <a href="/dashboard" className="text-gray-700 hover:text-gray-900">Back to Dashboard</a>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-4xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          <div className="bg-white shadow overflow-hidden sm:rounded-lg">
            <div className="px-4 py-5 sm:p-6">
              <h2 className="text-2xl font-bold mb-4">How to Use the Smart Email Assistant</h2>
              
              <div className="space-y-6">
                <div>
                  <h3 className="text-lg font-medium text-gray-900">Getting Started</h3>
                  <p className="mt-2 text-sm text-gray-600">
                    1. Start a chat with the bot on Telegram.<br/>
                    2. Use the /start command to initialize.<br/>
                    3. Connect your Gmail account via the login link.
                  </p>
                </div>

                <div>
                  <h3 className="text-lg font-medium text-gray-900">Natural Language Commands</h3>
                  <p className="mt-2 text-sm text-gray-600">
                    Chat naturally with the bot. Examples:<br/>
                    - "Show me my recent emails"<br/>
                    - "Email my boss about the project update"<br/>
                    - "Reply to the last email with 'Thanks!'"<br/>
                    - "Summarize this attachment"
                  </p>
                </div>

                <div>
                  <h3 className="text-lg font-medium text-gray-900">Settings</h3>
                  <p className="mt-2 text-sm text-gray-600">
                    Use /settings to toggle AI mode and voice preferences.<br/>
                    AI Mode: Enable intelligent responses<br/>
                    Voice: Choose between text and voice replies
                  </p>
                </div>

                <div>
                  <h3 className="text-lg font-medium text-gray-900">Contact Management</h3>
                  <p className="mt-2 text-sm text-gray-600">
                    The bot automatically learns your contacts from conversations.<br/>
                    Mention people by name: "Email Sarah about the meeting"
                  </p>
                </div>

                <div>
                  <h3 className="text-lg font-medium text-gray-900">Undo Actions</h3>
                  <p className="mt-2 text-sm text-gray-600">
                    After sending, deleting, or replying to emails, you'll see an Undo button for 4 seconds.
                  </p>
                </div>
              </div>

              <div className="mt-8 border-t border-gray-200 pt-6">
                <h3 className="text-lg font-medium text-gray-900">Contact Us</h3>
                <p className="mt-2 text-sm text-gray-600">
                  Need help? Contact our administrators:
                </p>
                <ul className="mt-2 text-sm text-gray-600">
                  {admins.map((admin, index) => (
                    <li key={index}>
                      {admin.name}: <a href={`mailto:${admin.email}`} className="text-blue-600 hover:text-blue-800">{admin.email}</a>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Help;