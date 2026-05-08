-- Insert your first Super Admin (Replace with your email)
INSERT INTO admin_users (email, role, created_at) 
VALUES ('muhammadsalmansarwarwattoo@gmail.com', 'super_admin', CURRENT_TIMESTAMP)
ON CONFLICT (email) DO NOTHING;