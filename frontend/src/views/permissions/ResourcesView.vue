<script setup lang="ts">
import ResourcePermissionsPanel from '../../components/ResourcePermissionsPanel.vue'
import PermissionGrantDialog from '../../components/permissions/PermissionGrantDialog.vue'
import { documentCollections, documents, loadingDocuments, selectedCollection } from '../../stores/documents'
import { collectionPermissionDialogVisible, collectionPermissionUserOptions, groups, loadingGroups, loadingPermissions, permissionDialogTitle, permissionDialogVisible, permissionUserOptions, selectedCollectionGroupPermissions, selectedCollectionUserPermissions, selectedGroupPermissions, selectedPermissions } from '../../stores/permissionAdmin'
import { grantCollectionGroup, grantCollectionUser, grantDocumentGroup, grantDocumentUser, loadPermissionAdminData, openCollectionPermissions, openPermissions, revokeCollectionGroupPermission, revokeCollectionUserPermission, revokeGroupPermission, revokePermission } from '../../stores/permissionActions'
</script>

<template>
<section class="view-stack">
            <ResourcePermissionsPanel
              :documents="documents"
              :collections="documentCollections"
              :loading="loadingDocuments || loadingGroups"
              @refresh="loadPermissionAdminData"
              @authorize-document="openPermissions"
              @authorize-collection="openCollectionPermissions"
            />

<PermissionGrantDialog
  v-model="permissionDialogVisible"
  :title="permissionDialogTitle"
  alert="权限在后端文档列表和 RAG 检索阶段都会生效。文档上传者默认拥有访问权限，不需要单独授权。"
  :loading="loadingPermissions"
  detailed
  :users="permissionUserOptions"
  :groups="groups"
  :user-grants="selectedPermissions"
  :group-grants="selectedGroupPermissions"
  :grant-user="grantDocumentUser"
  :grant-group="grantDocumentGroup"
  :revoke-user="revokePermission"
  :revoke-group="revokeGroupPermission"
  group-hint="适合把同一批文档开放给法规部、研发部等用户组。"
/>

<PermissionGrantDialog
  v-model="collectionPermissionDialogVisible"
  :title="selectedCollection ? `文档集授权：${selectedCollection.name}` : '文档集授权'"
  alert="集合权限会自动覆盖当前和后续移入该文档集的全部文档，并在后端文档列表与 RAG 检索阶段生效。"
  :loading="loadingPermissions"
  :users="collectionPermissionUserOptions"
  :groups="groups"
  :user-grants="selectedCollectionUserPermissions"
  :group-grants="selectedCollectionGroupPermissions"
  :grant-user="grantCollectionUser"
  :grant-group="grantCollectionGroup"
  :revoke-user="revokeCollectionUserPermission"
  :revoke-group="revokeCollectionGroupPermission"
  user-hint="写权限同时包含读取权限。"
  group-hint="部门成员会继承该文档集的权限。"
/>
</section>
</template>
