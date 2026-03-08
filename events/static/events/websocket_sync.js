/**
 * WebSocket Sync Listener for Real-Time Event Updates
 * Connects to Django Channels WebSocket and updates events when syncs complete
 */

(function() {
    'use strict';

    const WebSocketSyncListener = {
        ws: null,
        reconnectAttempts: 0,
        maxReconnectAttempts: 5,
        reconnectDelay: 3000, // Start with 3 seconds
        isConnecting: false,

        /**
         * Initialize WebSocket connection
         */
        init: function() {
            // Determine WebSocket protocol (ws or wss)
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/events/sync/`;

            console.log('[WebSocket] Attempting to connect to:', wsUrl);
            
            try {
                this.ws = new WebSocket(wsUrl);
                this.isConnecting = true;

                this.ws.onopen = () => this.onOpen();
                this.ws.onmessage = (event) => this.onMessage(event);
                this.ws.onerror = (error) => this.onError(error);
                this.ws.onclose = () => this.onClose();
            } catch (error) {
                console.error('[WebSocket] Failed to create WebSocket:', error);
                this.scheduleReconnect();
            }
        },

        /**
         * Handle WebSocket connection open
         */
        onOpen: function() {
            console.log('[WebSocket] Connected successfully');
            this.isConnecting = false;
            this.reconnectAttempts = 0;
            this.reconnectDelay = 3000; // Reset delay on successful connection
            this.showNotification('✓ Connected to sync server', 'success');
        },

        /**
         * Handle incoming WebSocket messages
         */
        onMessage: function(event) {
            try {
                const data = JSON.parse(event.data);
                console.log('[WebSocket] Received message:', data);

                if (data.type === 'sync_update') {
                    this.handleSyncUpdate(data);
                }
            } catch (error) {
                console.error('[WebSocket] Failed to parse message:', error, event.data);
            }
        },

        /**
         * Handle sync update from server
         */
        handleSyncUpdate: function(data) {
            const { events, timestamp, success_count, error_count } = data;
            
            console.log(`[Sync Update] ${success_count} events synced, ${error_count} errors`);

            if (events && events.length > 0) {
                this.showNotification(
                    `✓ Synced ${success_count} event${success_count !== 1 ? 's' : ''}`,
                    'success'
                );

                // Update event rows in the DOM
                events.forEach(event => {
                    this.updateEventInDOM(event);
                });

                // Dispatch custom event for other scripts to listen to
                window.dispatchEvent(new CustomEvent('eventsUpdated', { detail: { events, timestamp } }));
            }

            if (error_count > 0) {
                this.showNotification(
                    `⚠ ${error_count} error${error_count !== 1 ? 's' : ''} during sync`,
                    'warning'
                );
            }
        },

        /**
         * Update a single event in the DOM
         */
        updateEventInDOM: function(event) {
            const eventRow = document.querySelector(`[data-event-id="${event.id}"]`);
            
            if (!eventRow) {
                console.log(`[Update] Event row not found in DOM for event ${event.id}`);
                return;
            }

            console.log(`[Update] Updating event #${event.id} in DOM`);

            // Update category/title
            const titleCell = eventRow.querySelector('[data-field="title"]');
            if (titleCell && event.category_name) {
                titleCell.textContent = event.category_name;
            }

            // Update due date
            const dueCell = eventRow.querySelector('[data-field="due_date"]');
            if (dueCell && event.due_date) {
                dueCell.textContent = this.formatDate(event.due_date);
            }

            // Update calendar start time
            const startCell = eventRow.querySelector('[data-field="calendar_start_time"]');
            if (startCell && event.calendar_start_time) {
                startCell.textContent = `From: ${this.formatTime(event.calendar_start_time)}`;
            }

            // Update calendar end time
            const endCell = eventRow.querySelector('[data-field="calendar_end_time"]');
            if (endCell && event.calendar_end_time) {
                endCell.textContent = `To: ${this.formatTime(event.calendar_end_time)}`;
            }

            // Update status
            const statusCell = eventRow.querySelector('[data-field="status"]');
            if (statusCell && event.status) {
                statusCell.textContent = event.status;
                // Add status badge styling if available
                statusCell.className = `status-${event.status.toLowerCase()}`;
            }

            // Add visual highlight to indicate update
            eventRow.classList.add('just-updated');
            setTimeout(() => {
                eventRow.classList.remove('just-updated');
            }, 3000);
        },

        /**
         * Handle WebSocket errors
         */
        onError: function(error) {
            console.error('[WebSocket] Error occurred:', error);
            this.showNotification('⚠ Connection interrupted', 'warning');
        },

        /**
         * Handle WebSocket close
         */
        onClose: function() {
            console.log('[WebSocket] Connection closed');
            this.isConnecting = false;
            
            if (this.reconnectAttempts < this.maxReconnectAttempts) {
                this.scheduleReconnect();
            } else {
                console.error('[WebSocket] Max reconnection attempts reached');
                this.showNotification('✗ Sync connection failed', 'error');
            }
        },

        /**
         * Schedule reconnection attempt
         */
        scheduleReconnect: function() {
            this.reconnectAttempts++;
            console.log(
                `[Reconnect] Attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} ` +
                `in ${this.reconnectDelay}ms`
            );

            setTimeout(() => {
                this.init();
            }, this.reconnectDelay);

            // Exponential backoff: increase delay for next attempt
            this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 30000);
        },

        /**
         * Format date string to readable format
         */
        formatDate: function(dateStr) {
            try {
                const date = new Date(dateStr);
                return date.toLocaleDateString('en-ZA', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric'
                });
            } catch (error) {
                console.error('[Format] Invalid date:', dateStr);
                return dateStr;
            }
        },

        /**
         * Format time string to readable format (HH:MM)
         */
        formatTime: function(timeStr) {
            try {
                // Handle ISO datetime strings (e.g., "2026-03-08T14:30:00+00:00")
                if (timeStr && timeStr.includes('T')) {
                    const date = new Date(timeStr);
                    return date.toLocaleTimeString('en-ZA', { hour: '2-digit', minute: '2-digit', hour12: false });
                }
                // Handle HH:MM format
                const [hours, minutes] = timeStr.split(':');
                return `${hours}:${minutes}`;
            } catch (error) {
                console.error('[Format] Invalid time:', timeStr);
                return timeStr;
            }
        },

        /**
         * Show temporary notification
         */
        showNotification: function(message, type = 'info') {
            const notification = document.getElementById('sync-notification');
            
            if (!notification) {
                console.log('[Notification] Container not found, skipping:', message);
                return;
            }

            // Remove existing notification if present
            notification.classList.remove('show', 'success', 'warning', 'error', 'info');
            
            // Update content and styling
            notification.textContent = message;
            notification.classList.add(type);
            
            // Show notification
            setTimeout(() => {
                notification.classList.add('show');
            }, 10);

            // Auto-hide after 5 seconds
            setTimeout(() => {
                notification.classList.remove('show');
            }, 5000);
        }
    };

    // Initialize WebSocket on page load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            WebSocketSyncListener.init();
        });
    } else {
        WebSocketSyncListener.init();
    }

    // Expose to global scope for debugging and external access
    window.WebSocketSyncListener = WebSocketSyncListener;
})();
