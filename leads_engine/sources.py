"""Lead Radar sources for Northwest Indiana and Chicagoland.

Each market lists the public feeds that produce distress *signals* on a property
and the parcel/ownership feed used to resolve who owns it and where their mail goes.
Everything is official open data; nothing here is scraped from behind a login.
"""

MARKETS = [
    {
        "slug": "cook-county-il",
        "name": "Cook County",
        "state": "IL",
        "short": "Chicago & Cook County",
        "blurb": "Chicago building-code violations and vacant-building reports, matched to Cook County Assessor ownership records.",
        # Who owns it. Socrata, refreshed daily by the Cook County Assessor.
        "owner": {
            "host": "datacatalog.cookcountyil.gov",
            "dataset": "pabr-t5kh",           # Parcel Universe (current year only)
            "fallback": "3723-97qp",          # Parcel Addresses (all years)
            "city_field": "prop_address_city_name",
            "addr_field": "prop_address_full",
        },
        "signals": [
            {
                "key": "violation",
                "label": "Open code violation",
                "weight": 2,
                "host": "data.cityofchicago.org",
                "dataset": "22u3-xenr",
                "date": "violation_date",
                "where": "violation_status='OPEN'",
                "select": "id,violation_date,violation_description,inspection_category,department_bureau,address",
                "address": "address",
                "desc": "violation_description",
                "city": "CHICAGO",
            },
            {
                "key": "vacant",
                "label": "Vacant building report",
                "weight": 3,
                "host": "data.cityofchicago.org",
                "dataset": "v6vf-nfxy",
                "date": "created_date",
                "where": "upper(sr_type) like '%VACANT%' AND duplicate=false",
                "select": "sr_number,sr_type,created_date,status,street_address,zip_code",
                "address": "street_address",
                "desc": "sr_type",
                "city": "CHICAGO",
            },
            {
                "key": "nuisance",
                "label": "Nuisance / sanitation report",
                "weight": 1,
                "host": "data.cityofchicago.org",
                "dataset": "v6vf-nfxy",
                "date": "created_date",
                "where": "(upper(sr_type) like '%WEED%' OR upper(sr_type) like '%SANITATION CODE%' OR upper(sr_type) like '%NO WATER%') AND duplicate=false",
                "select": "sr_number,sr_type,created_date,status,street_address,zip_code",
                "address": "street_address",
                "desc": "sr_type",
                "city": "CHICAGO",
            },
        ],
    },
]

# Owner-name patterns that mean a company, bank or trust rather than a person.
ENTITY = r"\b(llc|l\.l\.c|inc|corp|co\b|company|ltd|lp|trust|trustee|tr\b|bank|n\.a\.|na\b|properties|holdings|investments?|realty|partners|lp|church|city of|county|association|hoa|condo)\b"

# Residential Cook County classes (2xx) and small multi-family; what investors want.
RESIDENTIAL = r"^2\d\d$"
