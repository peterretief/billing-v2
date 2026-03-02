# Reply-To Email Setup Guide

## Overview
Invoice emails sent through your app automatically include a **reply-to** address, allowing clients to reply directly to your business email.

## How It Works

1. **Business Email Field**: Set your business email in your profile settings
   - Navigate to: **Profile Settings** → **Business Email**
   - This email will be used as the reply-to address for all invoice emails

2. **Fallback**: If no business email is set, replies default to your account email

3. **Email Sending**: 
   - Invoices are sent from: `"Your Company Name" <system-email@app.com>`
   - Replies go to: Your **Business Email** (or account email if not set)

## Brevo Setup (Required for Replies to Work)

Brevo requires you to verify email addresses before they can receive replies:

### Step 1: Add Verified Sender
1. Log in to your [Brevo account](https://app.brevo.com)
2. Go to **Senders & Contacts** → **My Senders**
3. Click **Add a New Sender**
4. Enter your business email address
5. Brevo will send a verification email to that address
6. Click the verification link in the email

### Step 2: Update Your App Profile
1. In Billing Your Way, go to **Profile Settings**
2. Enter your verified business email in the **Business Email** field
3. Save your profile

### Step 3: Test
1. Create and email an invoice to a test client
2. Clients should be able to reply to that email
3. Replies will go to your business email address

## Multiple Verified Senders

If you have multiple business emails:
- Verify all of them in Brevo
- Update your app profile with the one you want to use for invoice replies
- You can change it anytime in your profile settings

## Important Notes

- ⚠️ **Verification Required**: Unverified emails in Brevo won't work as reply-to addresses
- ⚠️ **Different from Sender**: The app sends FROM the system email, but replies come to YOUR email
- ✅ **Automatic**: Once set up, all future invoice emails will use the reply-to address
- ✅ **Optional**: If not configured, clients can still reply to the system sender email

## Troubleshooting

**Clients can't reply to invoices?**
- Check if the business email is verified in Brevo
- Verify it's filled in your app Profile Settings
- Check spam/junk folders

**Want to change the reply-to address?**
- Update the Business Email field in Profile Settings
- Save
- Next invoices will use the new address

**How to see what's currently set?**
- Go to Profile Settings
- Look at the Business Email field
- That's what replies will go to
