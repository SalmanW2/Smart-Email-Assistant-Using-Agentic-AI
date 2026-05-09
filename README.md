# AI Email Assistant

An intelligent email management system powered by AI, featuring Telegram bot integration, voice processing, and comprehensive contact management.

## Features

### 🤖 AI-Powered Email Assistant
- Natural language processing with Google Gemini 2.0 Flash
- Intelligent email drafting and responses
- Email analysis and insights
- Conversation memory and context awareness

### 📧 Email Integration
- Secure Google OAuth 2.0 authentication
- Gmail API integration for email access
- Email caching and quick access
- Smart email categorization

### 👥 Contact Management
- AI-powered contact extraction from emails
- Contact relationship mapping
- Search and organization features
- Contact frequency tracking

### 📱 Telegram Bot Interface
- Intuitive chat-based interface
- Voice message processing
- Inline keyboards for quick actions
- Real-time notifications

### 🔊 Voice Processing
- Text-to-speech with Google Cloud TTS
- Speech-to-text with Google Cloud Speech
- Fallback voice processing with pyttsx3
- Multi-language support

### 👨‍💼 Admin Dashboard
- User management and approval system
- System statistics and analytics
- Admin authentication with PBKDF2 hashing
- Role-based access control

### 🛡️ Security & Reliability
- Supabase PostgreSQL with Row Level Security
- Service role key for backend operations
- "No-crash" database error handling
- Secure password hashing

## Architecture

### Database Layer
- **Supabase PostgreSQL**: Primary database with RLS
- **Async Operations**: Non-blocking database calls
- **Memory Management**: Conversation summaries for token optimization
- **Contact Mapping**: Relationship tracking between contacts

### API Layer
- **FastAPI**: Modern async web framework
- **RESTful Endpoints**: Clean API design
- **CORS Support**: Cross-origin resource sharing
- **Webhook Integration**: Telegram bot communication

### Bot Layer
- **Telegram Bot API**: Interactive chat interface
- **Command Handling**: Structured command processing
- **Callback Queries**: Inline keyboard interactions
- **Voice Processing**: Audio message handling

### AI Engine
- **Google Gemini 2.0**: Advanced language model
- **Context Awareness**: Memory-based conversations
- **Email Analysis**: Intelligent content processing
- **Response Generation**: Natural language responses

## Project Structure

```
backend/
├── main.py                 # FastAPI application entry point
├── config.py              # Environment configuration
├── auth.py                # Authentication endpoints
├── admin.py               # Admin dashboard endpoints
├── user.py                # User-specific endpoints
├── telegram_handler.py    # Telegram bot logic
├── ai_engine.py          # AI processing engine
├── voice_handler.py      # Voice processing utilities
└── db/
    ├── models.py         # Database operations
    ├── memory.py         # Conversation memory management
    └── contacts.py       # Contact relationship management

database/
├── schema.sql            # Database schema
└── seed.sql              # Initial data seeding

frontend/                  # React/Vite admin dashboard
requirements.txt           # Python dependencies
```

## Setup Instructions

### Prerequisites
- Python 3.10+
- PostgreSQL/Supabase account
- Google Cloud Platform account
- Telegram Bot Token

### Environment Configuration

Create a `.env` file in the backend directory:

```env
# Database
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token

# Google APIs
GOOGLE_API_KEY=your_gemini_api_key
GOOGLE_CLIENT_ID=your_oauth_client_id
GOOGLE_CLIENT_SECRET=your_oauth_client_secret
GOOGLE_REDIRECT_URI=your_redirect_uri

# Google Cloud (optional for voice)
GOOGLE_CLOUD_PROJECT=your_project_id

# Application
BASE_URL=https://your-domain.com
FRONTEND_URL=https://your-frontend-domain.com
SECRET_KEY=your-secret-key
DEBUG=false
PORT=8000
```

### Database Setup

1. Create a new Supabase project
2. Run the schema.sql file to create tables
3. Run the seed.sql file to add initial admin user
4. Update RLS policies as needed

### Installation

1. Clone the repository
2. Navigate to the backend directory
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the application:
   ```bash
   python main.py
   ```

### Telegram Bot Setup

1. Create a bot with @BotFather on Telegram
2. Set the webhook URL to your domain:
   ```
   https://your-domain.com/webhook/telegram
   ```

## API Endpoints

### Authentication
- `POST /api/auth/start-auth` - Start OAuth flow
- `GET /api/auth/oauth/callback` - OAuth callback
- `POST /api/auth/admin/login` - Admin login

### Admin
- `GET /api/admin/users` - List all users
- `POST /api/admin/users/action` - User actions (approve/block)
- `GET /api/admin/admins` - List admins
- `POST /api/admin/admins/add` - Add admin
- `GET /api/admin/stats` - System statistics

### User
- `GET /api/user/profile` - User profile
- `PUT /api/user/preferences` - Update preferences
- `GET /api/user/contacts` - List contacts
- `POST /api/user/contacts` - Add contact
- `PUT /api/user/contacts/{id}` - Update contact
- `DELETE /api/user/contacts/{id}` - Delete contact
- `GET /api/user/contacts/search` - Search contacts

## Security Features

- **Row Level Security**: Database-level access control
- **Service Role Key**: Backend admin operations bypass RLS
- **PBKDF2 Password Hashing**: Secure admin authentication
- **OAuth 2.0**: Secure Google account linking
- **Input Validation**: Pydantic models for data validation
- **Error Handling**: Comprehensive exception handling

## Performance Optimizations

- **Async Operations**: Non-blocking I/O throughout
- **Connection Pooling**: Efficient database connections
- **Memory Management**: Conversation summaries reduce token usage
- **Caching**: Email and contact data caching
- **Background Tasks**: Long-running operations don't block

## Development

### Running Tests
```bash
pytest
```

### Code Formatting
```bash
black .
isort .
```

### Linting
```bash
flake8 .
```

## Deployment

### Docker
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["python", "main.py"]
```

### Environment Variables
Ensure all required environment variables are set in production.

### Webhook Configuration
Configure Telegram webhooks to point to your production domain.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue on GitHub
- Check the documentation
- Review the code comments

## Roadmap

- [ ] Email threading and conversation grouping
- [ ] Advanced contact relationship analysis
- [ ] Multi-language support expansion
- [ ] Integration with additional email providers
- [ ] Mobile app development
- [ ] Advanced analytics dashboard