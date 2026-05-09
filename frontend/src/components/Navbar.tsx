import { Link } from 'react-router-dom';

const Navbar = () => {
  return (
    <nav className="bg-white shadow">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <Link to="/dashboard" className="text-xl font-semibold text-gray-900">
              Smart Email Assistant
            </Link>
          </div>
          <div className="flex items-center space-x-4">
            <Link to="/dashboard" className="text-gray-700 hover:text-gray-900">Dashboard</Link>
            <Link to="/help" className="text-gray-700 hover:text-gray-900">Help</Link>
          </div>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;