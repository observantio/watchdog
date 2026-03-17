"""
Shared Operations for the Ops files

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Iterable, List

from sqlalchemy.orm import Session


def group_id_strs(group_ids: Iterable[str] | None) -> List[str]:
    return [str(group_id) for group_id in (group_ids or [])]


def commit_session(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def update_hidden_members(hidden_by: Iterable[str] | None, user_id: str, hidden: bool) -> list[str]:
    hidden_list = [str(member) for member in (hidden_by or [])]
    if hidden:
        if user_id not in hidden_list:
            hidden_list.append(user_id)
    elif user_id in hidden_list:
        hidden_list.remove(user_id)
    return hidden_list
