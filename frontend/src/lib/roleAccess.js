// Point 45 + 46: Role-based route access for admin dashboard.
// - super_admin / admin: full access
// - parking_staff: /parking-scanner, /parking-report
// - bill_operator: /bills only (Point 46)
// - app_manager: /banners, /offers (Hot Deals), /events, /campaigns (Point 45)
// - call_centre / support_officer: legacy — full admin access for now

export const ROLE_ROUTES = {
  parking_staff: ['/parking-scanner', '/parking-report'],
  bill_operator: ['/bills'],
  app_manager: ['/banners', '/offers', '/events', '/campaigns'],
};

export const ROLE_LANDING = {
  parking_staff: '/parking-scanner',
  bill_operator: '/bills',
  app_manager: '/banners',
};

export function isPathAllowed(role, path) {
  const allowed = ROLE_ROUTES[role];
  if (!allowed) return true; // super_admin/admin/call_centre/support_officer → all
  return allowed.includes(path);
}

export function landingForRole(role) {
  return ROLE_LANDING[role] || '/';
}
