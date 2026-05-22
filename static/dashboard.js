async function loadMetrics() {

    try {

        const res = await fetch('/metrics/default');
        const data = await res.json();

        document.getElementById('total').innerText = data.total_leads;
        document.getElementById('hot').innerText = data.hot_leads;
        document.getElementById('warm').innerText = data.warm_leads;
        document.getElementById('cold').innerText = data.cold_leads;

    } catch (err) {
        console.error("Error loading metrics:", err);
    }
}

async function loadLeads() {

    try {

        const res = await fetch('/leads/default');
        const leads = await res.json();

        const table = document.getElementById('leadsTable');
        table.innerHTML = '';

        leads.reverse().forEach(lead => {

            let typeClass = 'cold';

            if (lead.lead_type === 'CALIENTE') typeClass = 'hot';
            if (lead.lead_type === 'TIBIO') typeClass = 'warm';

            table.innerHTML += `
                <tr>
                    <td>${lead.user_id}</td>
                    <td>${lead.message}</td>
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

window.onload = function () {
    loadMetrics();
    loadLeads();
};
