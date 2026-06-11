# FL Foreclosures — Diamond Home Buyers Intelligence Dashboard

On-demand scraper for floridapublicnotices.com pulling foreclosure sale notices
from the last 30 days for: Hillsborough, Polk, Marion, Orange, Duval, St. Lucie.

Extracted per record: defendant name(s), plaintiff, case number, property address,
city, state, zip, auction date/time, auction site (realforeclose.com link).

## Setup
1. Create a new public repo named `fl-foreclosures` at github.com/new
2. Upload all files from this folder (drag and drop everything EXCEPT the .github folder)
3. Create the workflow file manually: Add file -> Create new file -> name it
   `.github/workflows/scrape.yml` -> paste contents of that file -> Commit
4. Settings -> Pages -> Source: Deploy from a branch -> Branch: gh-pages -> Save
5. Actions tab -> enable workflows

## Run on demand
Actions -> "FL Foreclosures Scrape" -> Run workflow

Also runs automatically every Friday 6 AM CT (remove the `schedule:` block in
scrape.yml if you want manual-only).

Dashboard: https://jamoney711.github.io/fl-foreclosures/

## How the scraper works
1. Opens floridapublicnotices.com, searches "foreclosure"
2. Sets the date range to the last 30 days
3. Selects the county in the filter listbox, clicks Update
4. Opens the first result and walks every notice using the "Next Notice" button
5. Skips non-foreclosure notices (legal ads, hearings, tax deeds)
6. Parses each notice: the "Property Address:" label, "Plaintiff, v. ... Defendant(s)"
   block, case number, and the sale date that follows the "sell to the highest bidder"
   language (not the order date)

## If a county returns 0 records
The site may have changed its layout. The scraper saves a debug screenshot to
`data/debug_<county>_*.png` on failures — check that first.
