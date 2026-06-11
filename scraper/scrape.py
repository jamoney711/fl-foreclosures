import json,csv,time,re
from datetime import datetime,timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

TARGET_COUNTIES=["Hillsborough","Polk","Marion","Orange","Duval","St. Lucie"]

OUTPUT_DIR=Path(__file__).parent.parent/"data"
OUTPUT_DIR.mkdir(exist_ok=True)
BASE_URL="https://floridapublicnotices.com"
DAYS_BACK=30
MAX_NOTICES_PER_COUNTY=400

def parse_notice(text,newspaper="",pub_date="",subcategory=""):
    data={
        "defendant":"","plaintiff":"","case_number":"",
        "property_address":"","property_city":"","property_state":"FL","property_zip":"",
        "auction_date":"","auction_time":"","auction_site":"",
        "newspaper":newspaper,"publication_date":pub_date,"subcategory":subcategory
    }

    # Defendant(s): names between "v." and "Defendant"
    m=re.search(r"(?:Plaintiff[,;.]?\s*(?:vs?\.?|v[,.]))\s*(.+?)[,;.]?\s*Defendant",text,re.IGNORECASE|re.DOTALL)
    if m:
        d=re.sub(r"\s+"," ",m.group(1)).strip(" ,;.")
        # Drop trailing ET AL variants for the clean name but keep note
        d=re.sub(r"[,;]?\s*ET\.?\s*AL\.?$","",d,flags=re.IGNORECASE).strip(" ,;.")
        if 2<len(d)<200:
            data["defendant"]=d.title()

    # Plaintiff: the line immediately before "Plaintiff"
    m=re.search(r"([^\n]{3,150})\n\s*Plaintiff",text)
    if m:
        p=re.sub(r"\s+"," ",m.group(1)).strip(" ,;.")
        if 2<len(p)<150 and not re.match(r"CASE\s",p,re.IGNORECASE):
            data["plaintiff"]=p.title()

    # Case number
    m=re.search(r"CASE\s*(?:NO|NUMBER)[\.:\s]*([0-9]{2,4}-[A-Z]{2}-[0-9]{3,7}(?:\s*DIV\s*[A-Z0-9]+)?)",text,re.IGNORECASE)
    if m:
        data["case_number"]=m.group(1).strip()

    # Property Address: explicit label - the gold standard on this site
    m=re.search(r"Property\s+Address[:\s]+([^\n]+?)(?:\n|$)",text,re.IGNORECASE)
    if m:
        full=re.sub(r"\s+"," ",m.group(1)).strip(" .")
        # Try splitting: "17029 PEACEFUL VALLEY DR, WIMAUMA, FL 33598"
        am=re.match(r"(.+?),\s*([A-Za-z\s\.]+?),?\s*(?:Florida|FL)\.?\s*(\d{5})?",full)
        if am:
            data["property_address"]=am.group(1).strip().title()
            data["property_city"]=am.group(2).strip().title()
            if am.group(3):
                data["property_zip"]=am.group(3)
        else:
            data["property_address"]=full.title()

    # Fallback address pattern if no label
    if not data["property_address"]:
        m=re.search(r"(\d{2,6}\s+[A-Z0-9][A-Za-z0-9\s]{2,40}(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Circle|Cir|Way|Blvd|Boulevard|Place|Pl|Terrace|Ter|Trail|Trl|Loop)\.?)[,\s]+([A-Za-z\s]+?),?\s*(?:Florida|FL)\s*(\d{5})",text,re.IGNORECASE)
        if m:
            data["property_address"]=m.group(1).strip().title()
            data["property_city"]=m.group(2).strip().title()
            data["property_zip"]=m.group(3)

    # Auction date: first date appearing AFTER the sale-language anchor
    anchor=-1
    for kw in ["sell to the highest","public sale","best bidder","realforeclose","beginning at"]:
        pos=text.lower().find(kw)
        if pos!=-1:
            anchor=pos
            break
    dates=[(mm.start(),mm.group(1)) for mm in re.finditer(r"(?:on\s+)?([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",text)]
    chosen=""
    if anchor!=-1:
        after=[d for pos,d in dates if pos>anchor]
        if after:
            chosen=after[0]
    if not chosen:
        # Prefer a future date anywhere in the notice
        now=datetime.now()
        for pos,d in dates:
            try:
                if datetime.strptime(d,"%B %d, %Y")>now:
                    chosen=d
                    break
            except:
                continue
    if not chosen and dates:
        chosen=dates[0][1]
    data["auction_date"]=chosen

    tm=re.search(r"(?:beginning\s+at|at)\s+(\d{1,2}:\d{2}\s*[AaPp]\.?[Mm]\.?)",text)
    if tm:
        data["auction_time"]=tm.group(1).strip().upper().replace(".","")

    sm=re.search(r"((?:https?://)?(?:www\.)?[a-z0-9\-]+\.realforeclose\.com)",text,re.IGNORECASE)
    if sm:
        data["auction_site"]=sm.group(1)

    return data

def is_foreclosure_notice(text,subcategory):
    if subcategory and "foreclosure" in subcategory.lower():
        return True
    t=text.upper()
    return ("FORECLOSURE" in t or "NOTICE OF SALE" in t) and ("DEFENDANT" in t or "PLAINTIFF" in t)

def dump_debug(page,tag):
    try:
        path=OUTPUT_DIR/("debug_"+tag+".png")
        page.screenshot(path=str(path))
        print("    [debug] screenshot saved: "+path.name)
    except Exception as e:
        print("    [debug] screenshot failed: "+str(e))

def setup_search(page,county,date_from,date_to):
    """Run the search exactly like the recording: keyword + dates + county + Update."""
    page.goto(BASE_URL+"/",wait_until="domcontentloaded",timeout=45000)
    page.wait_for_load_state("networkidle",timeout=25000)
    time.sleep(2)

    # Dismiss any cookie/consent if present
    for sel in ["button:has-text('Accept')","button:has-text('OK')","button:has-text('Got it')"]:
        try:
            b=page.locator(sel)
            if b.count()>0 and b.first.is_visible():
                b.first.click()
                time.sleep(0.5)
        except:
            pass

    # Search keyword
    typed=False
    for sel in ["input[type='search']","input[placeholder*='earch']","input[type='text']"]:
        box=page.locator(sel)
        if box.count()>0:
            box.first.click()
            box.first.fill("foreclosure")
            box.first.press("Enter")
            typed=True
            break
    if not typed:
        print("    [WARN] search box not found")
    page.wait_for_load_state("networkidle",timeout=25000)
    time.sleep(2)

    # Date range: two text inputs showing dates mm/dd/yyyy
    date_inputs=page.locator("input").filter(has_text=re.compile(""))
    set_dates=False
    try:
        candidates=page.locator("input")
        idxs=[]
        for i in range(candidates.count()):
            v=candidates.nth(i).get_attribute("value") or ""
            if re.match(r"\d{2}/\d{2}/\d{4}",v):
                idxs.append(i)
        if len(idxs)>=2:
            candidates.nth(idxs[0]).evaluate(
                "(el,val)=>{el.value=val;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}",
                date_from)
            candidates.nth(idxs[1]).evaluate(
                "(el,val)=>{el.value=val;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}",
                date_to)
            set_dates=True
            print("    Date range set: "+date_from+" -> "+date_to)
    except Exception as e:
        print("    [WARN] date set: "+str(e))
    if not set_dates:
        print("    [WARN] could not set dates - using site default (last 35 days)")

    # County: multi-select listbox
    picked=False
    sels=page.locator("select")
    for i in range(sels.count()):
        try:
            opts=sels.nth(i).locator("option")
            labels=[opts.nth(j).text_content().strip() for j in range(min(opts.count(),100))]
            if county in labels or any(county in (l or "") for l in labels):
                sels.nth(i).select_option(label=county)
                picked=True
                break
        except:
            continue
    if not picked:
        # Listbox rendered as div list - click the item by text
        item=page.locator("li:has-text('"+county+"'), div[role='option']:has-text('"+county+"'), option:has-text('"+county+"')")
        if item.count()>0:
            item.first.click()
            picked=True
    if not picked:
        print("    [WARN] could not select county "+county)

    # Update button
    upd=page.locator("button:has-text('Update'), input[value='Update']")
    if upd.count()>0:
        upd.first.click()
    else:
        page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle",timeout=25000)
    time.sleep(2.5)

    # Report result count if visible
    try:
        body=page.locator("body").text_content() or ""
        m=re.search(r"Showing\s+\d+\s*-\s*\d+\s+of\s+(\d+)\s+results",body)
        if m:
            print("    Results reported by site: "+m.group(1))
    except:
        pass

def scrape_county(page,county,date_from,date_to):
    records=[]
    try:
        setup_search(page,county,date_from,date_to)
    except Exception as e:
        print("    ["+county+"] setup error: "+str(e))
        dump_debug(page,county+"_setup")
        return records

    # Open the first result card
    opened=False
    for sel in [".card",".notice-card","div[class*='card']","div[class*='result']"]:
        cards=page.locator(sel)
        if cards.count()>0:
            try:
                cards.first.click()
                opened=True
                break
            except:
                continue
    if not opened:
        # Click the first card-like heading
        h=page.locator("text=/Tampa Bay Times|Business Observer|LaGaceta|Sentinel|Orlando|Ledger/").first
        try:
            h.click()
            opened=True
        except Exception as e:
            print("    ["+county+"] could not open first notice: "+str(e))
            dump_debug(page,county+"_open")
            return records
    page.wait_for_load_state("networkidle",timeout=20000)
    time.sleep(1.5)

    # Walk notices with Next Notice button
    seen_hashes=set()
    count=0
    while count<MAX_NOTICES_PER_COUNTY:
        try:
            modal=page.locator(".modal, div[role='dialog'], div[class*='modal']")
            scope=modal.first if modal.count()>0 else page.locator("body")
            text=scope.text_content() or ""
            text=re.sub(r"\r","",text)

            h=hash(text[:500])
            if h in seen_hashes:
                print("    ["+county+"] repeated notice - stopping")
                break
            seen_hashes.add(h)
            count+=1

            # Header info
            newspaper=""
            pub_date=""
            subcat=""
            nm=re.search(r"(Tampa Bay Times|Business Observer[^\n]*|LaGaceta[^\n]*|Florida Sentinel[^\n]*|Orlando Sentinel|The Ledger|Ocala Star[^\n]*|Florida Times[^\n]*|St\. Lucie[^\n]*)",text)
            if nm:
                newspaper=nm.group(1).strip()
            pm=re.search(r"Publication Date\s*(\d{4}-\d{2}-\d{2})",text)
            if pm:
                pub_date=pm.group(1)
            sm=re.search(r"Subcategory\s*([A-Za-z\s\-]+?)(?:\n|Print|$)",text)
            if sm:
                subcat=sm.group(1).strip()

            if is_foreclosure_notice(text,subcat):
                parsed=parse_notice(text,newspaper,pub_date,subcat)
                parsed["county"]=county
                parsed["scraped_date"]=datetime.now().strftime("%Y-%m-%d")
                records.append(parsed)
                addr=parsed["property_address"] or "(no address)"
                print("    ["+county+"] #"+str(count)+" "+(parsed["defendant"][:40] or "?")+" | "+addr[:40])
            else:
                print("    ["+county+"] #"+str(count)+" skipped (not a foreclosure sale notice)")

            nxt=page.locator("text='Next Notice'").or_(page.locator("button:has-text('Next Notice'), a:has-text('Next Notice')"))
            if nxt.count()==0:
                print("    ["+county+"] no Next Notice - end of results")
                break
            nxt.first.click()
            time.sleep(1.2)
        except Exception as e:
            print("    ["+county+"] notice loop error: "+str(e))
            break

    # Close modal so the next county starts clean
    try:
        page.keyboard.press("Escape")
        time.sleep(0.5)
    except:
        pass

    print("    ["+county+"] "+str(len(records))+" foreclosure records")
    return records

def scrape_all(days_back=DAYS_BACK):
    print("FL scrape started - "+datetime.now().strftime("%Y-%m-%d %H:%M"))
    date_to=datetime.now()
    date_from=date_to-timedelta(days=days_back)
    df=date_from.strftime("%m/%d/%Y")
    dt=date_to.strftime("%m/%d/%Y")

    all_results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"]
        )
        context=browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width":1440,"height":900},
            extra_http_headers={"Accept-Language":"en-US,en;q=0.9"}
        )
        context.set_default_timeout(20000)
        page=context.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

        for i,county in enumerate(TARGET_COUNTIES):
            print("["+str(i+1)+"/"+str(len(TARGET_COUNTIES))+"] "+county+"...")
            try:
                recs=scrape_county(page,county,df,dt)
                all_results.extend(recs)
            except Exception as e:
                print("    COUNTY FAIL: "+str(e))
            time.sleep(2)
        browser.close()

    print("\nTotal: "+str(len(all_results))+" records")
    return all_results

def save_results(results,output_dir=OUTPUT_DIR):
    ts=datetime.now().strftime("%Y-%m-%d")
    json_path=output_dir/("fl_foreclosures_"+ts+".json")
    with open(json_path,"w") as f:
        json.dump(results,f,indent=2)
    csv_path=output_dir/("fl_foreclosures_"+ts+".csv")
    if results:
        fields=["county","defendant","plaintiff","case_number","property_address",
                "property_city","property_state","property_zip","auction_date",
                "auction_time","auction_site","newspaper","publication_date",
                "subcategory","scraped_date"]
        with open(csv_path,"w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
            w.writeheader()
            w.writerows(results)
    latest_path=output_dir/"latest.json"
    existing=[]
    if latest_path.exists():
        try:
            existing=json.load(open(latest_path))
        except:
            pass
    seen=set()
    merged=[]
    for r in existing+results:
        key=str(r.get("case_number",""))+"-"+str(r.get("property_address",""))+"-"+str(r.get("defendant",""))
        if key not in seen:
            seen.add(key)
            merged.append(r)
    cutoff=datetime.now()-timedelta(days=90)
    merged=[r for r in merged if datetime.strptime(r.get("scraped_date","2000-01-01"),"%Y-%m-%d")>cutoff]
    with open(latest_path,"w") as f:
        json.dump(merged,f,indent=2)
    print("Saved - latest.json: "+str(len(merged))+" total records")
    return json_path,csv_path

if __name__=="__main__":
    results=scrape_all()
    save_results(results)
