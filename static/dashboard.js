async function loadMetrics() {
    try {
        const res = await fetch('/metrics');
        const data = await res.json();

        if (data.error) {
            console.error("Metrics error:", data.error);
            return;
        }

        // ---------------- KPI ----------------
        document.getElementById('total').innerText = data.total_leads;
        document.getElementById('hot').innerText = data.hot_leads;
        document.getElementById('warm').innerText = data.warm_leads;
        document.getElementById('cold').innerText = data.cold_leads;

        const conversionEl = document.getElementById('conversion');
        if (conversionEl) {
            conversionEl.innerText = (data.conversion_rate || 0) + "%";
        }

        // ---------------- PLAN INFO (SAAS CORE) ----------------
        const planEl = document.getElementById('plan');
        const usageEl = document.getElementById('usage');
        const alertEl = document.getElementById('limitAlert');

        const used = data.used || 0;
        const limit = data.limit || 0;
        const plan = data.plan || "FREE";

        if (planEl) {
            planEl.innerText = plan;
        }

        if (usageEl) {
            usageEl.innerText = `${used} / ${limit} leads usados`;
        }

        // ---------------- ALERT SYSTEM ----------------
        if (alertEl) {

            if (limit > 0 && used >= limit) {
                alertEl.style.display = "block";
            } else if (limit > 0 && used >= limit * 0.8) {
                alertEl.style.display = "block";
                alertEl.innerText = "⚠️ Estás cerca del límite de tu plan.";
                alertEl.style.background = "#92400e";
            } else {
                alertEl.style.display = "none";
            }
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

            table.innerHTML += `
                <tr>
                    <td>${lead.user_id || '-'}</td>
                    <td>${lead.message || '-'}</td>
                    <td class="${typeClass}">${lead.lead_type}</td>
                    <td>${lead.score}</td>
                    <td>${lead.stage}</td>
                </tr>
            `;
        });

    } catch (err) {
        console.error("Error loading leads:", err);
    }
}

// -----------------------------
// AUTO REFRESH (SAAS FEEL PRO)
// -----------------------------
function startAutoRefresh() {
    loadMetrics();
    loadLeads();

    setInterval(() => {
        loadMetrics();
        loadLeads();
    }, 7000); // más “vivo” que antes
}

// -----------------------------
// INIT
// -----------------------------
window.onload = function () {
    startAutoRefresh();
};
