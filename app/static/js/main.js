/* ============================================================================
   EmlakAI - Main JavaScript
   ============================================================================ */

/* ============================================================================
   TOAST NOTIFICATIONS
   ============================================================================ */

function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideInUp 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

/* ============================================================================
   API HELPER FUNCTIONS
   ============================================================================ */

async function fetchAPI(endpoint, options = {}) {
    try {
        const response = await fetch(endpoint, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });

        if (!response.ok) {
            throw new Error(`API Error: ${response.statusText}`);
        }

        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

/* ============================================================================
   STATUS CHECKS
   ============================================================================ */

async function checkBackendHealth() {
    try {
        const response = await fetch('/api/agents/profile/1', { 
            method: 'HEAD' 
        }).catch(() => ({ ok: false }));
        return response.ok;
    } catch {
        return false;
    }
}

async function checkOllamaHealth() {
    try {
        const response = await fetch('http://localhost:11434/api/tags', {
            mode: 'no-cors'
        });
        return true;
    } catch {
        return false;
    }
}

/* ============================================================================
   UTILITY FUNCTIONS
   ============================================================================ */

function formatPrice(price) {
    if (!price) return '₺0';
    return '₺' + Math.round(price).toLocaleString('tr-TR');
}

function formatDuration(ms) {
    if (ms < 1000) return `${Math.round(ms)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
}

function formatDate(date) {
    const options = { 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric', 
        hour: '2-digit', 
        minute: '2-digit' 
    };
    return new Date(date).toLocaleDateString('tr-TR', options);
}

/* ============================================================================
   PAGE NAVIGATION
   ============================================================================ */

function navigateToPage(page) {
    window.location.href = page;
}

/* ============================================================================
   SMOOTH SCROLL BEHAVIOR
   ============================================================================ */

document.addEventListener('DOMContentLoaded', () => {
    // Highlight active nav link
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        const href = new URL(link.href).pathname;
        if (href === currentPath || (href === '/' && currentPath === '/')) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
});

/* ============================================================================
   ANALYZE PAGE HELPERS
   ============================================================================ */

function getUrlParam(param) {
    const params = new URLSearchParams(window.location.search);
    return params.get(param);
}

document.addEventListener('DOMContentLoaded', () => {
    // Pre-fill analyze inputs from URL params
    const listingId = getUrlParam('listing_id');
    const userId = getUrlParam('user_id');
    
    if (listingId && document.getElementById('listingId')) {
        document.getElementById('listingId').value = listingId;
    }
    if (userId && document.getElementById('userId')) {
        document.getElementById('userId').value = userId;
    }
});

/* ============================================================================
   LOADING ANIMATION
   ============================================================================ */

function createLoadingSpinner() {
    const spinner = document.createElement('div');
    spinner.className = 'loading-spinner';
    return spinner;
}

/* ============================================================================
   ADVANCED ANIMATIONS
   ============================================================================ */

// Staggered reveal animation for cards
function staggerReveal(elements, delay = 100) {
    elements.forEach((element, index) => {
        element.style.opacity = '0';
        element.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            element.style.animation = 'slideInUp 0.5s ease forwards';
        }, index * delay);
    });
}

// Intersection Observer for lazy animations
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -100px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.animation = 'slideInUp 0.6s ease forwards';
            observer.unobserve(entry.target);
        }
    });
}, observerOptions);

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.metric-card, .engine-card, .listing-card').forEach(card => {
        observer.observe(card);
    });
});

/* ============================================================================
   FORM HANDLING
   ============================================================================ */

document.addEventListener('DOMContentLoaded', () => {
    // Prevent form submission and handle with Enter key
    document.querySelectorAll('input[type="number"], input[type="text"]').forEach(input => {
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const button = input.parentElement.parentElement.querySelector('button');
                if (button) button.click();
            }
        });
    });
});

/* ============================================================================
   PERFORMANCE MONITORING
   ============================================================================ */

const performanceMetrics = {
    pageLoadStart: performance.now(),
    
    markMilestone(name) {
        const time = performance.now() - this.pageLoadStart;
        console.log(`[Milestone] ${name}: ${formatDuration(time)}`);
    },
    
    measureAPI(name, startTime) {
        const duration = performance.now() - startTime;
        console.log(`[API] ${name}: ${formatDuration(duration)}`);
        return duration;
    }
};

/* ============================================================================
   ERROR HANDLING
   ============================================================================ */

window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
    showToast('Beklenmeyen bir hata oluştu', 'error');
});

window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
    showToast('API hatası: ' + event.reason, 'error');
});

/* ============================================================================
   RETRY LOGIC FOR API CALLS
   ============================================================================ */

async function fetchWithRetry(url, options = {}, retries = 3) {
    for (let i = 0; i < retries; i++) {
        try {
            const response = await fetch(url, options);
            if (response.ok) {
                return await response.json();
            }
            if (response.status === 503) {
                // Service unavailable, retry
                if (i < retries - 1) {
                    await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
                    continue;
                }
            }
            throw new Error(`HTTP ${response.status}`);
        } catch (error) {
            if (i === retries - 1) throw error;
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
    }
}

/* ============================================================================
   RESPONSIVE BEHAVIOR
   ============================================================================ */

let isMobileView = window.innerWidth <= 768;

window.addEventListener('resize', () => {
    const wasMobile = isMobileView;
    isMobileView = window.innerWidth <= 768;
    
    if (wasMobile !== isMobileView) {
        console.log(`View changed to ${isMobileView ? 'mobile' : 'desktop'}`);
        // Trigger responsive layout updates if needed
    }
});

/* ============================================================================
   THEME/APPEARANCE
   ============================================================================ */

function initializeTheme() {
    // Check for saved theme preference or system preference
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = localStorage.getItem('theme') || (prefersDark ? 'dark' : 'light');
    
    // Always use dark theme for EmlakAI
    document.documentElement.setAttribute('data-theme', 'dark');
    localStorage.setItem('theme', 'dark');
}

document.addEventListener('DOMContentLoaded', initializeTheme);

/* ============================================================================
   SESSION MANAGEMENT
   ============================================================================ */

// Auto-save form inputs
function autoSaveFormInputs(formSelector) {
    const form = document.querySelector(formSelector);
    if (!form) return;
    
    form.querySelectorAll('input, select, textarea').forEach(field => {
        field.addEventListener('change', () => {
            const key = `form_${formSelector}_${field.name}`;
            localStorage.setItem(key, field.value);
        });
        
        // Restore saved values
        const key = `form_${formSelector}_${field.name}`;
        const saved = localStorage.getItem(key);
        if (saved) field.value = saved;
    });
}

/* ============================================================================
   ANALYTICS & TRACKING
   ============================================================================ */

function trackEvent(eventName, eventData = {}) {
    console.log(`[Event] ${eventName}`, eventData);
    
    // Could send to analytics service here
    // fetch('/api/analytics', {
    //     method: 'POST',
    //     body: JSON.stringify({ event: eventName, data: eventData })
    // });
}

/* ============================================================================
   COPY TO CLIPBOARD
   ============================================================================ */

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Kopyalandı!', 'success', 2000);
    }).catch(err => {
        console.error('Copy failed:', err);
        showToast('Kopyalama başarısız', 'error');
    });
}

/* ============================================================================
   DEBOUNCE & THROTTLE
   ============================================================================ */

function debounce(func, delay) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func(...args), delay);
    };
}

function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/* ============================================================================
   MODAL/DIALOG HELPERS
   ============================================================================ */

function showModal(title, content, actions = []) {
    // Could create a modal dialog
    console.log(`Modal: ${title}\n${content}`);
}

function closeModal() {
    // Close current modal if exists
}

/* ============================================================================
   EXPORT FUNCTIONS FOR TEMPLATES
   ============================================================================ */

window.EmlakAI = {
    showToast,
    fetchAPI,
    checkBackendHealth,
    checkOllamaHealth,
    formatPrice,
    formatDuration,
    formatDate,
    navigateToPage,
    staggerReveal,
    trackEvent,
    copyToClipboard,
    debounce,
    throttle
};

/* ============================================================================
   INITIALIZATION
   ============================================================================ */

console.log('EmlakAI Frontend Initialized');
console.log('Version: 1.0.0');
console.log('Theme: Dark | Accent: Teal');
