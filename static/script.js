const API_BASE_URL = '/api';

// Helper function to display results
function displayResult(elementId, data, type = 'info') {
    const element = document.getElementById(elementId);
    element.textContent = JSON.stringify(data, null, 2);
    element.className = type;
}

// Helper function to display errors
function displayError(elementId, error) {
    const element = document.getElementById(elementId);
    element.textContent = `Error: ${JSON.stringify(error, null, 2)}`;
    element.className = 'error';
}

// Helper function to show loading state
function setLoading(buttonElement, isLoading) {
    if (isLoading) {
        buttonElement.disabled = true;
        buttonElement.innerHTML += '<span class="loading"></span>';
    } else {
        buttonElement.disabled = false;
        const loading = buttonElement.querySelector('.loading');
        if (loading) loading.remove();
    }
}

// Query NotebookLM (stateless)
async function queryNotebookLM() {
    const resultElementId = 'query-result';
    const button = event.target;
    const query = document.getElementById('query-text').value;
    const notebooklm_url = document.getElementById('notebooklm-url').value;
    const resultElement = document.getElementById(resultElementId);

    if (!query) {
        displayError(resultElementId, { error: 'Query text is required' });
        return;
    }
     if (!notebooklm_url) {
        displayError(resultElementId, { error: 'NotebookLM URL is required' });
        return;
    }

    try {
        setLoading(button, true);
        
        resultElement.textContent = 'Submitting query... This may take up to a minute.';
        resultElement.className = 'info';
        
        const response = await fetch(`${API_BASE_URL}/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                query: query,
                notebooklm_url: notebooklm_url
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            displayError(resultElementId, data);
            return;
        }
        
        displayResult(resultElementId, data, 'success');
    } catch (error) {
        displayError(resultElementId, { error: error.message });
    } finally {
        setLoading(button, false);
    }
}
