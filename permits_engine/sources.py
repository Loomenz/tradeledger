"""Open-data permit feeds. Each maps a city's Socrata columns onto one schema.

Only business names go in `contractor`; owner and applicant names of private
people are never published.
"""

SOURCES = [
    {
        "slug": "austin", "city": "Austin", "state": "TX",
        "host": "data.austintexas.gov", "dataset": "3syk-w9eu", "date": "issue_date",
        "address": ["permit_location", "original_address1"],
        "desc": ["description"], "type": ["permit_type_desc", "work_class"],
        "value": ["total_job_valuation", "total_valuation_remodel", "building_valuation"],
        "contractor": ["contractor_company_name"], "zip": ["original_zip"],
        "link": "https://abc.austintexas.gov/web/permit/public-search-other",
    },
    {
        "slug": "chicago", "city": "Chicago", "state": "IL",
        "host": "data.cityofchicago.org", "dataset": "ydr8-5enu", "date": "issue_date",
        "address": [["street_number", "street_direction", "street_name"]],
        "desc": ["work_description"], "type": ["work_type", "permit_type"],
        "value": ["reported_cost", "total_fee"],
        "contractor": ["contact_1_name"], "contractor_type_key": "contact_1_type",
        "zip": ["community_area"], "link": "https://webapps1.chicago.gov/buildingrecords/",
    },
    {
        "slug": "seattle", "city": "Seattle", "state": "WA",
        "host": "data.seattle.gov", "dataset": "76t5-zqzr", "date": "issueddate",
        "address": ["originaladdress1"], "desc": ["description"],
        "type": ["permittypedesc", "permitclass"], "value": ["estprojectcost"],
        "contractor": ["contractorcompanyname"], "zip": ["originalzip"],
        "link": "https://services.seattle.gov/portal/",
    },
    {
        "slug": "los-angeles", "city": "Los Angeles", "state": "CA",
        "host": "data.lacity.org", "dataset": "pi9x-tg5x", "date": "issue_date",
        "address": ["primary_address"], "desc": ["work_desc"],
        "type": ["permit_type", "permit_sub_type"], "value": ["valuation"],
        "contractor": ["contractors_business_name", "contractor_business_name"], "zip": ["zip_code"],
        "link": "https://www.ladbsservices2.lacity.org/OnlineServices/",
    },
    {
        "slug": "new-orleans", "city": "New Orleans", "state": "LA",
        "host": "data.nola.gov", "dataset": "rcm3-fn58", "date": "issuedate",
        "address": ["address"], "desc": ["description"], "type": ["type"],
        "value": ["constrval"], "contractor": ["contractors", "contractor"], "zip": [],
        "link": "https://onestopapp.nola.gov/",
    },
    {
        "slug": "baton-rouge", "city": "Baton Rouge", "state": "LA",
        "host": "data.brla.gov", "dataset": "7fq7-8j7r", "date": "issueddate",
        "address": ["streetaddress", "address"], "desc": ["projectdescription"],
        "type": ["permittype"], "value": ["projectvalue"],
        "contractor": ["contractorname", "contractorcompanyname"], "zip": ["zip"],
        "link": "https://www.brla.gov/",
    },
    {
        "slug": "cambridge", "city": "Cambridge", "state": "MA",
        "host": "data.cambridgema.gov", "dataset": "qu2z-8suj", "date": "issue_date",
        "address": ["full_address"], "desc": ["detailed_description_of_work"],
        "type": [], "value": ["total_cost"], "contractor": ["firm_name", "contractor_company"], "zip": [],
        "link": "https://www.cambridgema.gov/inspection",
    },
]

# Trade keywords, matched against the lower-cased description + permit type.
TRADES = [
    ("roofing", "Roofing", ["reroof", "re-roof", "roofing", "shingle", "roof replace", "replace roof", "replace the roof", "roof repair", "new roof", "tear off", "tear-off", "roof covering", "remove existing roof", "roof over"]),
    ("solar", "Solar", ["solar", "photovoltaic", " pv ", "pv system"]),
    ("hvac", "HVAC", ["hvac", "furnace", "air condition", "heat pump", "mini split", "mini-split", "a/c", "ductwork", "condenser", "mechanical"]),
    ("plumbing", "Plumbing", ["plumb", "water heater", "sewer", "repipe", "backflow", "gas line", "fuel gas"]),
    ("electrical", "Electrical", ["electric", "panel", "service upgrade", "ev charger", "wiring", " meter "]),
    ("pools", "Pools & spas", ["pool", " spa ", "hot tub"]),
    ("windows-doors", "Windows & doors", ["window", " door", "doors", "skylight"]),
    ("remodel", "Remodeling", ["remodel", "renovat", "kitchen", "bathroom", "alteration", "interior", "addition"]),
    ("new-homes", "New homes & ADUs", ["new single family", "new residence", "new construction", "new two story", "new one story", "adu", "accessory dwelling", "new sfd", "new duplex"]),
    ("demolition", "Demolition", ["demolition", "demolish", "wreck", " demo "]),
    ("decks-fences", "Decks, fences & patios", ["deck", "fence", "patio", "pergola", "retaining wall"]),
    ("fire-safety", "Fire alarm & sprinkler", ["fire alarm", "sprinkler", "fire suppression"]),
    ("foundation", "Foundation repair", ["foundation repair", "underpin", " piers", "foundation stabiliz", "slab repair"]),
]
