`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useAuth } from '../contexts/AuthContext';

export function usePermissions() {
  const { user } = useAuth();
  
  const permissions = user?.permissions || [];
  
  const hasPermission = (permission) => {
    if (user?.is_superuser) return true;
    return permissions.includes(permission);
  };
  
  const hasAnyPermission = (permissionList) => {
    if (user?.is_superuser) return true;
    return permissionList.some(p => permissions.includes(p));
  };
  
  const hasAllPermissions = (permissionList) => {
    if (user?.is_superuser) return true;
    return permissionList.every(p => permissions.includes(p));
  };
  
  return {
    permissions,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    isSuperuser: user?.is_superuser || false,
    canManageUsers: hasPermission('manage:users'),
    canManageGroups: hasPermission('manage:groups'),
    canReadAlerts: hasPermission('read:alerts'),
    canWriteAlerts: hasPermission('write:alerts'),
    canDeleteAlerts: hasPermission('delete:alerts'),
    canReadChannels: hasPermission('read:channels'),
    canWriteChannels: hasPermission('write:channels'),
    canDeleteChannels: hasPermission('delete:channels'),
  };
}
