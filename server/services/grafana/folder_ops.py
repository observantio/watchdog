"""
Folder operations for Grafana integration, providing functions to extract folder UIDs from request paths and resolve folder UIDs based on folder IDs during dashboard creation. This module interacts with the Grafana API to retrieve folder information and ensures that folder-related operations are properly handled when creating or managing dashboards in Grafana, allowing for correct association of dashboards with their respective folders while also supporting error handling and logging for cases where folder resolution may fail.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Optional


def extract_folder_uid_from_path(service, path: str) -> Optional[str]:
    patterns = [
        r"^/grafana/dashboards/f/([^/?]+)",
        r"^/grafana/api/folders/([^/?]+)",
    ]
    import re
    for pattern in patterns:
        match = re.match(pattern, path)
        if match:
            return match.group(1)
    return None


async def resolve_folder_uid(service, folder_id: Optional[int]) -> Optional[str]:
    if not folder_id:
        return None
    try:
        folders = await service.grafana_service.get_folders()
        for folder in folders:
            if folder.id == folder_id:
                return folder.uid
    except Exception as exc:
        service.logger.debug("Unable to resolve folder uid for created dashboard: %s", exc)
    return None
