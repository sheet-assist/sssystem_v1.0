# Cases User Guide

**Role Required**: Cases Only, Prospects & Cases, or Admin

---

## Quick Start

1. Click **Cases** in navigation bar
2. Use search/filter to find cases:
   - **Case #** - Case reference number
   - **Type** - Case type
   - **Status** - Current status
   - **County** - County name
   - **State** - State name/abbreviation
3. Results show in card grid
4. Click **View Details** to open case

---

## Navigation

### Main Views

**All Cases** → **Filter by Criteria** → **View Details**

### Quick Menu

| View | Purpose |
|------|---------|
| All Cases | Browse all cases with search/filter |
| My Cases | Cases assigned to you only |
| Open Cases | Active cases needing work |
| Closed Cases | Completed/resolved cases |

---

## Finding Cases

### Search & Filter

**Available Search Fields**:
- **Case #** - Search by case number
- **Type** - Filter by case type
- **Status** - Filter by status (open, closed, pending)
- **County** - Text search by county name
- **State** - Text search by state name or abbreviation

### Search Example 1: Find Cases in Miami-Dade

1. Click **Cases**
2. In filter bar:
   - County: `Miami-Dade`
   - State: `FL`
3. Click **Filter**
4. Grid shows matching cases

### Search Example 2: Find Your Open Cases

1. Click **My Cases**
2. Status: `Open`
3. Click **Filter**
4. Shows only your assigned open cases

### Clear All Filters

Click **Clear** button to reset fields and show all cases.

---

## Case Details

### View Information

Click **View Details** on any case card to see:
- **Case information** (number, type, status, county)
- **Financial summary** (amounts, values)
- **Parties** (plaintiff, defendant, other involved)
- **Timeline** (dates, deadlines)
- **Status history** (all changes)
- **Notes** (communications, research, follow-ups)

### Case Card Shows

| Field | Information |
|-------|-------------|
| Case # | System case reference |
| Type | Case type (Deed, Lien, Sale, etc.) |
| Status | Current status (Open, Closed, Pending) |
| County | County and state |
| Assigned | User responsible for case |

---

## Managing Cases

### Add Note

1. Open case detail view
2. Scroll to notes section
3. Click **Add Note**
4. Enter note content:
   - **Communication** - Contact with parties
   - **Follow-up** - Action reminder
   - **Research** - Investigation findings
5. Click **Save**

### Update Status

1. Open case detail
2. Click **Update Status** button
3. Choose new status:
   - **Open** - Active case
   - **Pending** - Waiting on something
   - **In Progress** - Currently working
   - **Closed** - Completed
4. Save changes

### Update Case Details

1. Open case detail view
2. Click **Edit** button
3. Modify fields as needed:
   - Case type
   - Financial amounts
   - Assigned user
   - Deadline dates
4. Click **Save**

### Create Follow-up

1. Open case detail
2. In notes section, click **Add Note**
3. Select **Follow-up** type
4. Enter follow-up details with date
5. Save - note appears in timeline

---

## Case Types

| Type | Description |
|------|-------------|
| Tax Deed | Property sale for unpaid taxes |
| Tax Lien | Lien filed for unpaid taxes |
| Sheriff Sale | Property sale via sheriff |
| Mortgage Foreclosure | Lender foreclosure action |
| Other | Custom case types |

---

## Case Status Workflow

```
Open → In Progress → Pending → Closed
                      ↓
                   Follow-up
```

### Status Meanings

| Status | When Used |
|--------|-----------|
| Open | Just created, needs assignment |
| In Progress | Actively working on it |
| Pending | Waiting for external action |
| Closed | Completed or abandoned |

---

## Case Card Display

### Understanding Cards

Each case card shows:
- **Header** - Case #, Type badge, Status badge
- **Location** - County and state
- **Assigned To** - Current owner
- **Created** - When added to system
- **Updated** - Last change date
- **Action Button** - View full details

### Color Coding

**Status Badge Colors**:
- **Green** = Open (active)
- **Blue** = In Progress (working)
- **Yellow** = Pending (waiting)
- **Gray** = Closed (done)

**Type Badge Colors**:
- **Blue** = Tax Deed
- **Purple** = Tax Lien
- **Orange** = Sheriff Sale
- **Green** = Mortgage Foreclosure

### Compact Display

Cards optimized for space:
- 2-3 columns per screen
- Essential info always visible
- Responsive to device size

---

## Timeline & History

### Case History

Click **View History** on case detail:
- **All changes** to case data
- **Status transitions** with dates
- **All notes** chronologically
- **User actions** who did what
- **Assignments** changes

### Timeline Benefits

- See case progress over time
- Track all communications
- Review decision reasoning
- Audit trail for compliance

---

## Assigning Cases

### Assign to Team Member

1. Open case detail
2. Click **Assign** button
3. Select user from dropdown:
   - Shows only users with case access
4. Click **Confirm**
5. User is notified of assignment

### Reassign Case

1. Open case detail
2. Click current assignee name
3. Click **Reassign**
4. Select new user
5. Save - old and new user are notified

### Bulk Assign

1. Go to case list view
2. Check multiple case boxes (if available)
3. Click **Assign** action
4. Select user to assign all to
5. Confirm

---

## Common Tasks

### Task 1: Find All Tax Deed Cases in Florida

1. Click **Cases**
2. Filter:
   - Type: `Tax Deed`
   - State: `Florida` or `FL`
3. Click **Filter**
4. Review results

### Task 2: Find Your Open Cases

1. Click **My Cases**
2. Status: `Open`
3. Click **Filter**
4. Your open cases appear
5. Sort by county if needed

### Task 3: Close a Completed Case

1. Open case detail
2. Click **Update Status**
3. Select **Closed**
4. Add closing note: `[CLOSED] - Case resolved on [date]`
5. Save

### Task 4: Add Communication Note

1. Open case detail
2. Scroll to notes
3. Click **Add Note**
4. Select **Communication** type
5. Add details:
   - Who you contacted
   - What was discussed
   - Next steps
6. Save

### Task 5: Set Follow-up Reminder

1. Open case detail
2. Click **Add Note**
3. Select **Follow-up** type
4. Enter:
   - Action needed
   - Date for follow-up
   - Contact method (email, phone, visit)
5. Save - note appears in timeline

---

## Pagination

**Items per page**: 20-25 cases

**Navigation**:
- Previous/Next buttons at bottom
- Skip to page number
- Shows current position (e.g., "Page 1 of 3")

---

## Filtering Combinations

### Scenarios

| Goal | Filter By |
|------|-----------|
| Your open tax deeds | My Cases + Type: Tax Deed + Status: Open |
| All pending cases | Status: Pending |
| County workload | County: [name] → See all cases |
| Recent updates | Sort by updated date (newest first) |

---

## Data Fields Reference

### Status Fields

| Status | Icon | Meaning |
|--------|------|---------|
| Open | 🟢 | Active case |
| In Progress | 🔵 | Actively working |
| Pending | 🟡 | Awaiting action |
| Closed | ⚫ | Completed |

### Type Fields

| Type | Description |
|------|-------------|
| TD | Tax Deed sales |
| TL | Tax Liens |
| SS | Sheriff Sales |
| MF | Mortgage Foreclosure |

### Financial Fields

| Field | Meaning |
|-------|---------|
| Bid Amount | Winning bid amount |
| Assessed Value | Tax assessor value |
| Lien Amount | Amount of lien/judgment |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Can't find case | Clear filters and try broader search |
| Search returns no results | Try filtering by just type or just state |
| Case info not updating | Refresh page or logout/login |
| Can't edit case | May need higher permissions - contact admin |
| Notes not saving | Check internet connection, try again |
| Cases disappear | Logout/login to refresh, or clear cache |

---

## Tips & Best Practices

✅ **Best Practices**:
- Add notes after each contact/action
- Update status as case progresses
- Set timely follow-ups
- Keep detailed communication notes
- Review history before taking action
- Use consistent note format

❌ **Avoid**:
- Leaving cases unassigned
- Not updating status when case closes
- Adding vague notes
- Forgetting follow-ups
- Losing track of deadlines

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| F5 | Refresh page |
| Ctrl+F | Find in page |
| Enter | Submit filter/search |
| Esc | Close modal/dialog |

---

## Contact & Support

**Issues or Questions?**
- Contact your administrator
- Check system documentation
- Review this user guide

---

**Version**: 1.0 | **Status**: ✅ Complete
