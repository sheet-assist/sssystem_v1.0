# Admin User Guide

**Role Required**: Admin Only

---

## Quick Start

1. Click **Settings** in navigation bar
2. Choose management area:
   - **Manage Users** - User accounts and roles
   - **Scrape URLs** - County scraping configuration
   - **Filter Criteria** - Prospect qualification rules
3. Perform needed actions
4. System changes take effect immediately

---

## Navigation

### Admin Views

**Settings Dashboard** → **Management Areas** → **Perform Action**

### Admin Menu

| View | Purpose |
|------|---------|
| Users | Create, edit, assign roles to users |
| Scrape URLs | Configure county web scraping sources |
| Filter Criteria | Define prospect qualification rules |
| Settings | System configuration |

---

## User Management

### View All Users

1. Click **Settings**
2. Click **Manage Users**
3. Users display in cards organized by role
4. Cards show: name, username, role, email, phone, join date

### User Cards by Role

**Role Sections**:
- **Admin** - Full system access
- **Prospects & Cases** - Both modules
- **Cases Only** - Cases module only
- **Prospects Only** - Prospects module only

### Search Users

1. Go to user management
2. Use browser find (Ctrl+F) to search by:
   - Name
   - Username
   - Email

---

## Create New User

### Steps

1. Click **Settings** → **Manage Users**
2. Click **Add New User** button
3. Fill form:
   - **First Name** - User first name
   - **Last Name** - User last name
   - **Username** - Unique login name (auto-generated)
   - **Email** - User email address
   - **Role** - Choose access level
   - **Phone** (optional) - Contact number
   - **Active** - Check if user can login
4. Click **Save**

### User Roles

| Role | Prospects | Cases | Settings |
|------|-----------|-------|----------|
| Prospects Only | ✅ | ❌ | ❌ |
| Cases Only | ❌ | ✅ | ❌ |
| Prospects & Cases | ✅ | ✅ | ❌ |
| Admin | ✅ | ✅ | ✅ |

### Role Selection Guidelines

**Use** "Prospects Only" **for**: Sales/research-focused team
**Use** "Cases Only" **for**: Legal/closing specialists
**Use** "Prospects & Cases" **for**: Versatile team members
**Use** "Admin" **for**: Managers/configuration personnel

---

## Edit User

### Steps

1. Click **Settings** → **Manage Users**
2. Find user card
3. Click **Edit** button (pencil icon)
4. Modify as needed:
   - Name fields
   - Email address
   - Phone number
   - Role (dropdown)
   - Active status (checkbox)
5. Click **Save**

### One-Time Password Reset

1. Edit user account
2. Note: Contact user directly to set new password using Django admin (if needed)
3. User can reset via "Forgot Password" link

### Deactivate User

1. Edit user account
2. Uncheck **Active** checkbox
3. Click **Save**
4. User cannot login but account preserved

### Reactivate User

1. Edit user account
2. Check **Active** checkbox
3. Click **Save**

---

## Assign User Role

### Change User's Role

1. Click **Settings** → **Manage Users**
2. Find user card
3. Click **Edit**
4. Change **Role** dropdown
5. Click **Save**
6. User's access updates immediately

### Role Change Examples

**From**: "Prospects Only" → **To**: "Prospects & Cases"
- Result: User now sees both modules

**From**: "Prospects & Cases" → **To**: "Admin"
- Result: User gets full system access + settings

**From**: Any → **To**: "Cases Only"
- Result: User sees only cases module

---

## Scrape URLs Management

### What Are Scrape URLs?

County-specific web addresses where case data is scraped from courts.

### View Scrape URLs

1. Click **Settings**
2. Click **Scrape URLs**
3. URLs display in card grid
4. Cards show: county name, URL type, state, URL link, date updated

### Filter Scrape URLs

1. Go to **Scrape URLs**
2. Use filter form:
   - **County** - Search by county name
   - **State** - Search by state
   - **URL Type** - Filter by type (TD, TL, SS, MF)
   - **Active Status** - Show only active/inactive
3. Click **Filter**
4. Results update

### Search Example

**Task**: Find all scrape URLs for Tax Deed sources in Florida

1. Click **Scrape URLs**
2. Filter:
   - County: (leave blank for all)
   - State: `Florida` or `FL`
   - URL Type: `Tax Deed`
   - Active: Check to show only active
3. Click **Filter**

---

## Add Scrape URL

### Steps

1. Click **Scrape URLs**
2. Click **Add Scrape URL** button
3. Fill form:
   - **State** - Select from dropdown
   - **County** - Dropdown updates after state selected
   - **URL Type** - Choose case type (TD, TL, SS, MF)
   - **Base URL** - Paste full URL
   - **Active** - Check to enable scraping
   - **Notes** (optional) - Scraper instructions or details
4. Click **Save**

### URL Requirements

- Must be valid HTTP/HTTPS URL
- Should link to actual county data page
- Include any search parameters if needed
- Test URL before saving (verify it works)

### URL Type Codes

| Code | Type |
|------|------|
| TD | Tax Deed |
| TL | Tax Lien |
| SS | Sheriff Sale |
| MF | Mortgage Foreclosure |

---

## Edit Scrape URL

### Steps

1. Go to **Scrape URLs**
2. Find URL card
3. Click **Edit** button
4. Modify fields:
   - County, state, type
   - Base URL
   - Active status
   - Notes
5. Click **Save**

### Common Edits

**URL Changes**: County changed data source location
→ Update URL field

**Deactivate**: County no longer uses this scraper
→ Uncheck **Active** checkbox

**Add Notes**: Document special instructions
→ Add to **Notes** field

---

## Delete Scrape URL

### Steps

1. Go to **Scrape URLs**
2. Find URL card
3. Click **Delete** button
4. Confirm deletion (no undo)
5. URL removed from system

### Before Deleting

⚠️ **Check**:
- Are there active scraping jobs using this URL?
- Have cases been created from this source?
- Do you have backup URL for this county?

---

## Filter Criteria Management

### What Is Filter Criteria?

Rules that automatically qualify/disqualify prospects based on financial data.

### View Criteria Rules

1. Click **Settings**
2. Click **Filter Criteria**
3. Rules display as cards
4. Each card shows rule condition and thresholds

### Create Filter Rule

1. Go to **Filter Criteria**
2. Click **Add Rule** button
3. Fill form:
   - **Field** - Choose field to evaluate (bid amount, assessed value, etc.)
   - **Operator** - Select condition (>, <, =, ≠)
   - **Value** - Enter threshold amount
   - **Action** - Qualify or Disqualify prospect
   - **Active** - Enable rule
4. Click **Save**

### Example Rules

**Rule 1**: "Bid Amount > $50,000" → Qualify
**Rule 2**: "Assessed Value < $20,000" → Disqualify
**Rule 3**: "Lien Amount > $100,000" → Qualify

---

## Edit Filter Rule

### Steps

1. Go to **Filter Criteria**
2. Find rule card
3. Click **Edit**
4. Modify:
   - Field being evaluated
   - Condition (operator)
   - Threshold value
   - Action (qualify/disqualify)
5. Click **Save**

### Rule Changes Apply Immediately

Updated prospects are re-evaluated with new rules.

---

## Delete Filter Rule

### Steps

1. Go to **Filter Criteria**
2. Find rule card
3. Click **Delete**
4. Confirm deletion
5. Rule removed, prospects re-evaluated

---

## System Settings

### Access Settings

1. Click **Settings** in navigation
2. System settings appear on main page
3. Options include:
   - Default pagination size
   - Email notifications
   - Data export formats
   - System features

---

## User Role Permissions Matrix

### Complete Reference

| Feature | Prospects Only | Cases Only | Both Modules | Admin |
|---------|---|---|---|---|
| View Prospects | ✅ | ❌ | ✅ | ✅ |
| Edit Prospects | ✅ | ❌ | ✅ | ✅ |
| Create Cases from Prospects | ✅ | ❌ | ✅ | ✅ |
| View Cases | ❌ | ✅ | ✅ | ✅ |
| Edit Cases | ❌ | ✅ | ✅ | ✅ |
| View Settings | ❌ | ❌ | ❌ | ✅ |
| Manage Users | ❌ | ❌ | ❌ | ✅ |
| View/Edit Scrape URLs | ❌ | ❌ | ❌ | ✅ |
| View/Edit Filter Criteria | ❌ | ❌ | ❌ | ✅ |

---

## Data Management

### Export Data

1. Click **Settings** → **Data Management**
2. Choose export format:
   - CSV (spreadsheet)
   - JSON (system integration)
   - Excel (preferred for reports)
3. Select date range
4. Click **Export**
5. File downloads to your computer

### Backup Database

1. Contact technical support
2. Request database backup
3. Backups retained for 30 days

### Import Data

1. Click **Settings** → **Data Import**
2. Select file to import
3. Map columns to system fields
4. Preview data
5. Click **Import**

---

## Monitoring & Maintenance

### System Health Check

1. Click **Settings**
2. Look for **System Status** section
3. Should show:
   - Database connected ✅
   - All modules loaded ✅
   - Scraping service running ✅

### View Error Logs

1. Click **Settings** → **System Logs**
2. See recent system events
3. Errors highlighted in red
4. Filter by date and severity

### Common Issues

| Issue | Solution |
|-------|----------|
| Scraper not running | Reset scraper service (contact admin support) |
| Slow system performance | Clear cache, restart application |
| User can't login | Verify account active status, reset password |
| Search not working | Ensure search index is updated |

---

## Common Admin Tasks

### Task 1: Onboard New Team Member

1. Create user account with correct role
2. Verify email sent to user
3. User sets their password via email link
4. Assign initial prospects/cases if needed
5. Confirm access is working

### Task 2: Configure Scraping for New County

1. Find county web data source
2. Go to **Scrape URLs**
3. Add new URL entry:
   - State: Select state
   - County: Select county
   - Type: Choose case type
   - URL: Paste full URL
   - Active: Check
4. Save - scraping begins immediately

### Task 3: Deactivate Departed Employee

1. Go to **Users**
2. Find user card
3. Click **Edit**
4. Uncheck **Active**
5. Click **Save**
6. User can no longer login
7. Reassign their prospects/cases to others

### Task 4: Set Up Prospect Qualification Rules

1. Go to **Filter Criteria**
2. Add rule for each criterion:
   - Rule 1: Bid Amount threshold
   - Rule 2: Assessed Value threshold
   - Rule 3: Lien Amount threshold
3. Set each to Qualify or Disqualify
4. Activate all rules
5. Prospects auto-qualify/disqualify

### Task 5: Generate Monthly Report

1. Click **Reports** (if available)
2. Select date range (last month)
3. Filter by:
   - Prospects added
   - Cases created
   - Sales closed
4. Generate report
5. Export to Excel
6. Share with management

---

## Security Best Practices

✅ **Do**:
- Use strong passwords (min 12 chars, mix of types)
- Change password every 90 days
- Deactivate unused accounts immediately
- Review user access monthly
- Keep scrape URLs up to date
- Backup data regularly
- Monitor error logs

❌ **Don't**:
- Share admin credentials
- Use test data in production
- Delete old data without backup
- Enable scraping for inactive counties
- Leave test accounts active
- Ignore security warnings

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| F5 | Refresh page |
| Ctrl+F | Find on page |
| Ctrl+P | Print current page |
| Ctrl+E | Export data |
| Esc | Close modal/dialog |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| User can't access settings | Verify user role is "Admin" |
| Scrape URL won't save | Verify URL is valid HTTP/HTTPS |
| Filter criteria not applying | Ensure rule is marked "Active" |
| Changes not appearing | Refresh page or clear browser cache |
| User login problem | Check if account is "Active" |

---

## Support & Resources

### Getting Help

- Review system documentation in `/docs/`
- Check this guide's troubleshooting section
- Contact technical support
- Review system logs for errors

### Documentation Files

- `/docs/README.md` - System overview
- `/docs/PROSPECTS_USER.md` - Prospects user guide
- `/docs/CASES_USER.md` - Cases user guide
- `/docs/ADMIN_USER.md` - This file

---

## Advanced Topics

### Custom Scraper Rules

**Contact admin support** to:
- Add new county sources
- Create custom scraper patterns
- Configure data transformations
- Set up automated daily scraping

### Bulk Operations

**Available for admins**:
- Bulk change user role
- Bulk activate/deactivate users
- Bulk reassign cases
- Bulk update prospects

---

**Version**: 1.0 | **Status**: ✅ Complete
