async function loadMetrics() {
    try {
        const res = await fetch('/metrics');
        const data = await res.json();

        if (data.error) {
            console.error("Metrics error:", data.error);
            return;
        }

        document.getElementById('total').innerText = data.total_leads;
        document.getElementById('hot').innerText = data.hot_leads;
        document.getElementById('warm').innerText = data.warm_leads;
        document.getElementById('cold').innerText = data.cold_leads;

        // 🔥 NUEVO: conversion rate (SAAS VALUE METRIC)
        const conversionEl = document.getElementById('conversion');
        if (conversionEl) {
            conversionEl.innerText = (data.conversion_rate || 0) + "%";
        }

    } catch (err) {
        console.error("Error loading metrics:", err);
    }
}

async function loadLeads() {
    try {
        const res = await fetch('/leads');
        const leads = await res.json();

        if (leads.error) {
            console.error("Leads error:", leads.error);
            return;
        }

        const table = document.getElementById('leadsTable');

        if (!table) return;

        table.innerHTML = '';

        leads.reverse().forEach(lead => {

            let typeClass = 'cold';

            if (lead.lead_type === 'CALIENTE') typeClass = 'hot';
            if (lead.lead_type === 'TIBIO') typeClass = 'warm';

            const row = `
                <tr>
                    <td>${lead.user_id || '-'}</td>
                    <td>${lead.message || '-'}</td>
                    <td class="${typeClass}">${lead.lead_type}</td>
                    <td>${lead.score}</td>
                    <td>${lead.stage}</td>
                </tr>
            `;

            table.innerHTML += row;
        });

    } catch (err) {
        console.error("Error loading leads:", err);
    }
}

// -----------------------------
// AUTO REFRESH (SAAS FEEL)
// -----------------------------
function startAutoRefresh() {
    loadMetrics();
    loadLeads();

    setInterval(() => {
        loadMetrics();
        loadLeads();
    }, 8000); // cada 8 segundos
}

// -----------------------------
// INIT
// -----------------------------
window.onload = function () {
    startAutoRefresh();
};
