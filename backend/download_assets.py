import os
import urllib.request
import logging
from backend.config import settings

logger = logging.getLogger("posted.download_assets")

ASSETS = {
    "images": {
        "pu-logo.svg": "/profiles/ps/themes/ps_base/images/pu-logo.svg",
        "caarms_0.png": "/sites/g/files/toruqf4381/files/caarms_0.png"
    },
    "css": {
        "bootstrap.min.css": "/profiles/ps/themes/ps_base/bootstrap/css/bootstrap.min.css",
        "base_styles.css": "/profiles/ps/themes/ps_base/css/styles.css",
        "tiger_styles.css": "/profiles/ps/themes/ps_tiger/css/styles.css",
        "align_header.css": "/sites/g/files/toruqf4381/files/asset_injector/css/align_header_text-bed7c47f6c4723a74065f8c1cfc5bee1.css",
        "site_title.css": "/sites/g/files/toruqf4381/files/asset_injector/css/site_title_text_color-749e66b00b967fe37b1748755082e289.css",
        "sponsorship.css": "/sites/g/files/toruqf4381/files/asset_injector/css/sponsorship_disclaimer_footer_style-5365f584d8994480f50b7b80f6653256.css"
    }
}

def download_assets(force=False):
    # Determine base directory
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(os.path.dirname(backend_dir), "frontend", "static")
    
    headers = {
        settings.bypass_header_name: settings.bypass_header_value,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    logger.info(f"Syncing static assets to: {static_dir}")
    
    for folder, files in ASSETS.items():
        dest_folder = os.path.join(static_dir, folder)
        os.makedirs(dest_folder, exist_ok=True)
        
        for name, relative_url in files.items():
            dest_file = os.path.join(dest_folder, name)
            if os.path.exists(dest_file) and not force:
                logger.info(f"Asset '{name}' already exists locally. Skipping download.")
                continue
                
            full_url = f"{settings.target_host}{relative_url}"
            logger.info(f"Downloading asset from {full_url} to {dest_file}...")
            try:
                req = urllib.request.Request(full_url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    with open(dest_file, "wb") as f:
                        f.write(response.read())
                logger.info(f"Successfully downloaded: {name}")
            except Exception as e:
                logger.error(f"Failed to download asset '{name}' from {full_url}: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    download_assets(force=True)
