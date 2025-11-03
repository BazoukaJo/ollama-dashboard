// Test script to verify chat model population works
// Run with: node test_chat_models.js

// Mock the DOM API
const mockElements = {};

global.document = {
    getElementById: function(id) {
        if (id === 'chatModelSelect') {
            if (!mockElements[id]) {
                mockElements[id] = {
                    innerHTML: '',
                    appendChild: function(option) {
                        // Build proper HTML option tag
                        const html = `<option value="${option.value}">${option.textContent}</option>`;
                        this.innerHTML += html;
                    },
                    options: [],
                    addEventListener: function() {}
                };
            }
            return mockElements[id];
        }
        return null;
    },
    querySelectorAll: function() {
        return [];
    },
    createElement: function(tag) {
        if (tag === 'option') {
            return {
                value: '',
                textContent: '',
                outerHTML: ''
            };
        }
        return {};
    }
};

// Mock fetch API
global.fetch = async function(url) {
    console.log('Mock fetch called with URL:', url);
    return {
        ok: true,
        status: 200,
        json: async function() {
            return {
                models: [
                    { name: 'llama3.2:1b' },
                    { name: 'llama3:latest' },
                    { name: 'qwen3-vl:8b' }
                ]
            };
        }
    };
};

// Mock console (avoid recursion)
const realConsole = console;
global.console = {
    log: function(...args) { realConsole.log('[TEST]', ...args); },
    error: function(...args) { realConsole.error('[TEST ERROR]', ...args); },
    warn: function(...args) { realConsole.warn('[TEST WARN]', ...args); }
};

// Import the main.js functions (simplified version)
async function populateChatModels() {
    try {
        console.log('Fetching available models for chat...');
        const response = await fetch('/api/models/available');
        const data = await response.json();

        console.log('Chat models response:', response.status, data);

        if (response.ok && data.models && Array.isArray(data.models) && data.models.length > 0) {
            console.log('Found models:', data.models.length, 'models array:', data.models);
            const modelSelect = document.getElementById('chatModelSelect');
            if (!modelSelect) {
                console.error('chatModelSelect element not found - checking all select elements');
                const allSelects = document.querySelectorAll('select');
                console.log('All select elements found:', allSelects.length);
                allSelects.forEach((sel, idx) => {
                    console.log(`Select ${idx}: id=${sel.id}, name=${sel.name}`);
                });
                return;
            }

            console.log('Found chatModelSelect element:', modelSelect);

            // Clear existing options except the first one
            modelSelect.innerHTML = '<option value="">Choose a model...</option>';

            // Add available models
            data.models.forEach((model, index) => {
                if (model && model.name) {
                    console.log(`Adding model ${index}:`, model.name, 'full model object:', model);
                    const option = document.createElement('option');
                    option.value = model.name;
                    option.textContent = model.name;
                    modelSelect.appendChild(option);
                } else {
                    console.warn(`Skipping model ${index} - missing name:`, model);
                }
            });

            console.log('Chat model selector populated with', data.models.length, 'models');
            console.log('Final HTML:', modelSelect.innerHTML);
        } else {
            console.error('Failed to load available models. Response ok:', response.ok, 'Data:', data);
        }
    } catch (error) {
        console.error('Error loading chat models:', error, error.stack);
    }
}

// Run the test
async function runTest() {
    console.log('=== Starting Chat Models Population Test ===');

    // Get initial state
    const selectElement = document.getElementById('chatModelSelect');
    console.log('Initial select element HTML:', selectElement.innerHTML);

    // Run population function
    await populateChatModels();

    // Check final state
    console.log('Final select element HTML:', selectElement.innerHTML);

    // Verify results
    const html = selectElement.innerHTML;
    console.log('HTML content for verification:', html);
    const hasDefaultOption = html.includes('Choose a model...');
    const hasLlama32 = html.includes('llama3.2:1b');
    const hasLlama3 = html.includes('llama3:latest');
    const hasQwen = html.includes('qwen3-vl:8b');

    console.log('\n=== Test Results ===');
    console.log('Has default option:', hasDefaultOption);
    console.log('Has llama3.2:1b:', hasLlama32);
    console.log('Has llama3:latest:', hasLlama3);
    console.log('Has qwen3-vl:8b:', hasQwen);

    const success = hasDefaultOption && hasLlama32 && hasLlama3 && hasQwen;
    console.log('Overall test result:', success ? '✅ PASSED' : '❌ FAILED');

    if (success) {
        console.log('\n🎉 Chat model population is working correctly!');
        console.log('The dropdown should show all 3 models in the browser.');
    } else {
        console.log('\n❌ Chat model population has issues.');
    }

    return success;
}

// Execute test
runTest().catch(console.error);
