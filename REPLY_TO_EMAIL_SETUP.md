# Reply-To Email Setup Guide

## Overview
Invoice emails sent through your app automatically include a **reply-to** address, allowing clients to reply directly to your business email.

**Good news**: Reply-to addresses **do NOT require Brevo verification**. This feature works out of the box!

## How It Works

1. **Business Email Field**: Set your business email in your profile settings
   - Navigate to: **Profile Settings** → **Business Email**
   - This email will be used as the reply-to address for all invoice emails

2. **Fallback**: If no business email is set, replies default to your account email

3. **Email routing:**
   - Invoices sent FROM: `"Your Company Name" <system-email@app.com>` (requires Brevo verification)
   - Replies go TO: Your **Business Email** (NO Brevo setup needed)

## Quick Start (2 Steps)

### Step 1: Set Business Email in Your App
1. In Billing Your Way, go to **Profile Settings**
2. Enter your business email in the **Business Email** field
3. Save your profile
4. Done! Replies will go to this address

### Step 2: Verify Your App's Sender Email (One-Time, Only if Not Done)
1. Log in to your [Brevo account](https://app.brevo.com)
2. Go to **Senders & Contacts** → **My Senders**
3. Add and verify the sender email (the system email)
4. This is for the FROM address of invoices
5. Reply-to does NOT need verification

## Email Flow Details

```
┌─────────────────────────────────────────────────────────┐
│ Invoice Email Lifecycle                                 │
├─────────────────────────────────────────────────────────┤
│ FROM: system-email@app.com (verified in Brevo)         │
│ TO: client@company.com                                  │
│ REPLY-TO: your-business@email.com (any email OK)       │
├─────────────────────────────────────────────────────────┤
│ When client clicks Reply:                               │
│ → Compose window opens with TO: your-business@email.com │
│ → Their reply arrives in your email inbox              │
│ → You respond directly from your email                  │
└─────────────────────────────────────────────────────────┘
```

## Brevo Policy Details

Brevo's policy on reply-to addresses:

| Setting | Required to Verify? | Where It Goes |
|---------|-------------------|-------|
| **FROM Address** | ✅ YES | Brevo verified senders list |
| **REPLY-TO Address** | ❌ NO | Your profile settings in this app |

**Why the difference?**
- FROM address is controlled by Brevo - they need to verify you're authorized to send from it
- REPLY-TO is just an email header - any address can be used
- Brevo doesn't control where replies go - your mail server does

## Change Reply-To Address Anytime

To change where replies go:
1. Update **Profile Settings** → **Business Email**
2. Save
3. Next invoices will use the new reply-to address
4. No Brevo changes needed

## Important Notes

- 📧 **Easy to Change**: Update anytime in Profile Settings
- ✉️ **No Brevo Verification Needed**: Unlike FROM address, reply-to is unrestricted
- ⚠️ **Monitor Your Inbox**: Make sure you're checking the reply-to email address for responses
- 🔒 **Domain Reputation**: For best deliverability, configure SPF/DKIM/DMARC records
- 🔄 **Automatic**: Once set, all invoices use this reply-to

## Troubleshooting

**Clients can't reply to invoices?**
- Check Profile Settings → Business Email is not empty
- Check that the email address is correct
- Check your email provider's spam/blocked settings

**Replies ending up in spam?**
- This is a domain reputation issue, not a reply-to configuration issue
- Configure SPF/DKIM/DMARC records in your domain's DNS
- Contact your domain registrar or email provider for help

**Want to change where replies go?**
- Update the Business Email field in Profile Settings
- Save
- Future invoices will route replies to the new address
- Old invoices still use the old address

**Sending fails but reply-to seems fine?**
- This could be a sender verification issue (FROM address)
- Check that your sender email is verified in Brevo
- The reply-to address is NOT the issue - it works with any email
