# Surplus Squad System Documentation

**Version**: 1.0  
**Last Updated**: February 2026

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [User Roles Overview](#user-roles-overview)
3. [Quick Links](#quick-links)
4. [System Features](#system-features)
5. [Need Help?](#need-help)

---

## Getting Started

### Login
- Visit the login page
- Enter your **username** and **password**
- Click **Login**

### First Steps
- Your **role** determines what features you can access
- Check your **User Profile** dropdown (top right) to see your current role
- The **Navigation Bar** shows only features available to your role

**Your Role:**
- **Prospects Only** → Browse and manage prospects
- **Cases Only** → Browse and manage cases  
- **Prospects and Cases** → Access both features
- **Admin** → Full system access including configuration

---

## User Roles Overview

### 👤 Prospects Only Users
**Access**: Prospects module only

**What You Can Do**:
- Search and filter prospects by county, state, and criteria
- View prospect details, history, and notes
- Manage prospect research and transitions
- Assign prospects to work on

**View Navigation**: Click **Prospects** in navbar

**Dashboard**: Shows all prospects with filtering options

---

### 📁 Cases Only Users
**Access**: Cases module only

**What You Can Do**:
- Search and filter cases by type, status, county
- View case details and history
- Add notes and follow-ups to cases
- Update case status

**View Navigation**: Click **Cases** in navbar

**Dashboard**: Shows all cases organized in compact card grid

---

### 📊 Prospects and Cases Users
**Access**: Both Prospects and Cases modules

**Combined Features**:
- Full access to Prospects module
- Full access to Cases module
- Can convert prospects into cases in workflow

**Navigation**: Both **Prospects** and **Cases** appear in navbar

---

### ⚙️ Admin Users
**Access**: Everything + Administration features

**What You Can Do**:
- All prospect and case features
- **Scraper Management** - Configure and run scraping jobs
- **Settings** - Manage criteria, URLs, users
- **County URLs** - Configure county-specific scraping URLs
- **Filter Criteria** - Define rules for prospect qualification
- **User Management** - Create, edit, assign roles

**Administration**: Click **Settings** in navbar for full control

---

## Quick Links

| Feature | Role | Path |
|---------|------|------|
| Prospects | Prospects+/Both/Admin | Navbar → Prospects |
| Cases | Cases+/Both/Admin | Navbar → Cases |
| Settings | Admin | Navbar → Settings |
| Scraper | Admin | Navbar → Scraper |
| Profile | All | Dropdown Menu → Profile |
| Users | Admin | Settings → Manage Rules → User List |

---

## System Features

### 🔍 Search & Filter
**Available on all list views**:
- **Text search fields** for quick lookup
- **Status/Type filters** for categorization
- **County/State search** for location filtering
- **Clear button** to reset all filters

### 📇 Card Grid Layout
**Compact, organized display**:
- Information grouped in visual cards
- Hover effects show details
- Action buttons easily accessible
- Color-coded badges for status

### 🔐 Role-Based Access
**Security feature**:
- Users see only permitted features
- Direct URL access blocked for unauthorized roles
- Navbar adapts to user role
- Admin-only views protected

### 💾 Data Management
- All changes saved immediately
- History tracked for records
- Pagination for large lists (20-25 items per page)
- Bulk operations available in some modules

---

## Need Help?

### Common Tasks

**Finding a Prospect/Case**:
1. Go to Prospects or Cases list
2. Use search fields at top (Case#, County, State)
3. Click Filter to apply
4. Result cards appear in grid below

**Editing User Roles**:
1. Go to Settings → User List
2. Find user by role section
3. Click Edit button on user card
4. Change Role dropdown
5. Click Save Changes

**Viewing Your Profile**:
1. Click your name in top-right dropdown
2. Click Profile
3. View your current role and permissions

### Troubleshooting

| Issue | Solution |
|-------|----------|
| "Access Denied" error | Check your role - feature may require different permission level |
| Can't find navbar links | You don't have permission - role doesn't include that feature |
| Filters not working | Clear all fields with Clear button, then reapply one at a time |
| Page not loading | Refresh page (F5) or logout/login |

### Contact Admin

For role changes, permissions issues, or access problems:
- Ask your system administrator to update your user role
- Admin can edit user permissions in Settings → User List

---

## System Architecture

**Database**: SQLite (auto-created, auto-maintained)

**User Model**: 
- One user account
- One profile with role assignment
- Permissions determined by role

**Access Control**:
- LoginRequiredMixin - Must be logged in
- RoleSpecificMixin - Feature access by role
- AdminRequiredMixin - Admin features only

---

## Document Index

**User-Specific Guides**:
- [Prospects User Guide](PROSPECTS_USER.md) - Complete prospects feature guide
- [Cases User Guide](CASES_USER.md) - Complete cases feature guide
- [Admin User Guide](ADMIN_USER.md) - Administration and configuration

**Quick Start**:
- [Getting Started Guide](GETTING_STARTED.md) - 5-minute setup

---

**Last Reviewed**: February 10, 2026  
**Status**: ✅ Production Ready
