from todos.calendar_utils import get_google_contacts_list
from django.contrib.auth import get_user_model
from clients.models import Client

User = get_user_model()
user = User.objects.filter(username='peter').first()

if user:
    print("\n" + "="*60)
    print("📇 GOOGLE CONTACTS DEBUG")
    print("="*60 + "\n")
    
    # Get all contacts from Google
    contacts = get_google_contacts_list(user)
    print(f"Total Google Contacts: {len(contacts)}\n")
    
    # Get existing client emails
    existing_clients = Client.objects.filter(user=user).values_list('email', flat=True)
    print(f"Existing Clients: {list(existing_clients)}\n")
    
    # Show contacts that WOULD be available for import
    print("✅ CONTACTS AVAILABLE FOR IMPORT (last 10):")
    available = []
    for contact in contacts:
        if contact.get('email') and contact['email'] not in existing_clients:
            available.append(contact)
    
    if available:
        for contact in available[-10:]:
            print(f"  ✓ {contact.get('name'):<30} | {contact.get('email', 'NO EMAIL'):<30} | {contact.get('phone', '—')}")
    else:
        print("  (None - all contacts either have no email or are already clients)\n")
    
    # Show ALL contacts (for debugging)
    print("\n📋 ALL GOOGLE CONTACTS (last 10):")
    for i, contact in enumerate(contacts[-10:], 1):
        email_status = contact.get('email') or "(NO EMAIL)"
        already_client = " ⚠️ ALREADY A CLIENT" if contact.get('email') in existing_clients else ""
        print(f"  {i}. {contact.get('name'):<30} | {email_status:<30}{already_client}")
        
else:
    print("User not found")
