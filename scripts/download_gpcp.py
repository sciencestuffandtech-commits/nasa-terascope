import earthaccess

earthaccess.login()

hits = earthaccess.search_data(
    short_name="GPCPMON",
    version="3.3",
    temporal=("2001-01-01", "2025-12-31"),
)
print("files found:", len(hits))
earthaccess.download(hits, "data/raw/gpcp")
