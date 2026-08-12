/**
 * Cloud Control Panel - Main Entry Point
 * ES6 Module that imports all feature modules and attaches to window for onclick handlers.
 */
import { state, showToast, escapeHtml, logActivity } from './js/utils.js';
import { authenticate, logout } from './js/auth.js';
import { showScreen, goBackToAccounts, goBackToInstances, goBackFromGroup } from './js/navigation.js';
import { loadAccounts, openAccount, showAddAccountForm, cancelAccountForm, saveAccount, deleteAccount, editAccount } from './js/accounts.js';
import { refreshInstances, openInstance, startCurrentInstance, stopCurrentInstance, updateCurrentInstance, openCurrentDashboard, clearActivity } from './js/instances.js';
import { openGroup, startCurrentGroup, stopCurrentGroup, showAddGroupForm, cancelGroupForm, saveGroup, deleteGroup, editGroup } from './js/groups.js';
import { showAddInstanceForm, showInlineGroupCreate, cancelInstanceForm, saveInstance, deleteInstance, editInstance } from './js/admin.js';
import { openSettingsPanel, closeSettingsPanel, toggleSettingsSection, exportConfig, importConfig } from './js/settings.js';
import { showAddRuleForm, editRule, saveRule, toggleRule, deleteRule, cancelRuleForm } from './js/scheduler.js';
import { showAddChannelForm, editChannel, saveChannel, toggleChannel, deleteChannel, testChannel, updateChannelFields, cancelChannelForm } from './js/notifications.js';
import { loadCosts } from './js/costs.js';
import { showAddKeyForm, cancelKeyForm, saveKey, copyKey, closeKeyResult, deleteKey, toggleAllAccounts, editKeyPermissions, updateKeyPermissions } from './js/keys.js';

// Attach all functions to window for HTML onclick handlers
Object.assign(window, {
    authenticate, logout,
    showScreen, goBackToAccounts, goBackToInstances, goBackFromGroup,
    loadAccounts, openAccount, showAddAccountForm, cancelAccountForm, saveAccount, deleteAccount, editAccount,
    openInstance, startCurrentInstance, stopCurrentInstance, updateCurrentInstance, openCurrentDashboard, clearActivity,
    openGroup, startCurrentGroup, stopCurrentGroup, showAddGroupForm, cancelGroupForm, saveGroup, deleteGroup, editGroup,
    showAddInstanceForm, showInlineGroupCreate, cancelInstanceForm, saveInstance, deleteInstance, editInstance,
    openSettingsPanel, closeSettingsPanel, toggleSettingsSection, exportConfig, importConfig,
    showAddRuleForm, editRule, saveRule, toggleRule, deleteRule, cancelRuleForm,
    showAddChannelForm, editChannel, saveChannel, toggleChannel, deleteChannel, testChannel, updateChannelFields, cancelChannelForm,
    showAddKeyForm, cancelKeyForm, saveKey, copyKey, closeKeyResult, deleteKey, toggleAllAccounts, editKeyPermissions, updateKeyPermissions,
    showToast, escapeHtml, logActivity
});

// Init
document.addEventListener("DOMContentLoaded", () => {
    const savedKey = localStorage.getItem("ccp-api-key");
    if (savedKey) {
        state.apiKey = savedKey;
        loadAccounts();
    }
    document.getElementById("api-key-input").addEventListener("keypress", (e) => {
        if (e.key === "Enter") authenticate();
    });
});
