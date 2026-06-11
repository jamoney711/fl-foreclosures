import sys,json,shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0,str(Path(__file__).parent))
from scrape import scrape_all,save_results

def build_dashboard_data(data_dir):
    latest_path=data_dir/"latest.json"
    if not latest_path.exists():
        print("No latest.json - skipping dashboard build")
        return None
    with open(latest_path) as f:
        records=json.load(f)

    county_map={}
    city_map={}
    auction_map={}
    for r in records:
        county=r.get("county","Unknown")
        city=(r.get("property_city","") or "Unknown").strip() or "Unknown"
        ad=r.get("auction_date","")
        county_map.setdefault(county,{"count":0,"cities":set()})
        county_map[county]["count"]+=1
        county_map[county]["cities"].add(city)
        city_map.setdefault(city,{"count":0,"county":county})
        city_map[city]["count"]+=1
        if ad:
            auction_map[ad]=auction_map.get(ad,0)+1
    for c in county_map:
        county_map[c]["cities"]=sorted(county_map[c]["cities"])

    out={
        "generated_at":datetime.now().isoformat(),
        "total_records":len(records),
        "county_summary":county_map,
        "city_summary":city_map,
        "auction_calendar":auction_map,
        "records":records
    }
    out_path=data_dir/"dashboard_data.json"
    with open(out_path,"w") as f:
        json.dump(out,f,indent=2)
    dash_dir=Path(__file__).parent.parent/"dashboard"
    dash_dir.mkdir(exist_ok=True)
    shutil.copy(out_path,dash_dir/"dashboard_data.json")
    print("Dashboard data: "+str(len(records))+" records, "+str(len(county_map))+" counties")
    return out

def main():
    print("="*60)
    print("FL Foreclosures Pipeline - "+datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("="*60)
    data_dir=Path(__file__).parent.parent/"data"
    data_dir.mkdir(exist_ok=True)

    print("\n[Step 1] Scraping floridapublicnotices.com...")
    results=scrape_all()
    if results:
        save_results(results,data_dir)
    else:
        print("WARNING: no results - building dashboard with existing data")

    print("\n[Step 2] Building dashboard data...")
    build_dashboard_data(data_dir)
    print("Pipeline complete.")

if __name__=="__main__":
    main()
