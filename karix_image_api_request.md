# Karix WhatsApp Image API - Sample JSON Payloads

This document contains sample JSON payloads to request Karix to enable image sending 
capability for the CP67 Mall WhatsApp Business Account.

## Request to Enable Image Sending

Please enable image sending capability for our WhatsApp Business Account using the 
following configurations:

### Option 1: Base64 Image Payload
```json
{
  "message": {
    "channel": "WABA",
    "content": {
      "preview_url": false,
      "type": "IMAGE",
      "image": {
        "data": "<BASE64_ENCODED_IMAGE_STRING>",
        "caption": "Your parking QR code for CP67 Mall"
      }
    },
    "recipient": {
      "to": "919876543210",
      "recipient_type": "individual",
      "reference": {}
    },
    "sender": {
      "from": "919876543210"
    },
    "preferences": {
      "webHookDNId": "1001"
    }
  },
  "metaData": {
    "version": "v1.0.9"
  }
}
```

### Option 2: Image URL Payload (if Base64 is not supported)
```json
{
  "message": {
    "channel": "WABA",
    "content": {
      "preview_url": false,
      "type": "IMAGE",
      "image": {
        "link": "https://example.com/path/to/image.png",
        "caption": "Your parking QR code for CP67 Mall"
      }
    },
    "recipient": {
      "to": "919876543210",
      "recipient_type": "individual",
      "reference": {}
    },
    "sender": {
      "from": "919876543210"
    },
    "preferences": {
      "webHookDNId": "1001"
    }
  },
  "metaData": {
    "version": "v1.0.9"
  }
}
```

### Option 3: Media ID Payload (if pre-uploaded media is required)
```json
{
  "message": {
    "channel": "WABA",
    "content": {
      "preview_url": false,
      "type": "IMAGE",
      "image": {
        "id": "<MEDIA_ID>",
        "caption": "Your parking QR code for CP67 Mall"
      }
    },
    "recipient": {
      "to": "919876543210",
      "recipient_type": "individual",
      "reference": {}
    },
    "sender": {
      "from": "919876543210"
    },
    "preferences": {
      "webHookDNId": "1001"
    }
  },
  "metaData": {
    "version": "v1.0.9"
  }
}
```

## Use Case

We need to send **QR code images** to customers for:
1. **Parking Entry QR** - When customer enters CP67 Mall parking, they scan our WhatsApp QR 
   and we need to send them a unique QR code image that they show at the exit counter.

2. The QR codes are dynamically generated PNG images (Base64 encoded) approximately 10-15KB each.

## Current Error

When attempting to send images via the API endpoint:
`POST https://rcmapi.instaalerts.zone/services/rcm/sendMessage`

We receive: `400 - Invalid JSON input. Please check the request format.`

## Questions for Karix

1. What is the correct JSON format for sending images via WhatsApp?
2. Do you support Base64-encoded images in the request body, or do images need to be 
   hosted at a URL first?
3. Is there a separate media upload API we need to use before sending images?
4. Are there any size limits for images?

## Contact

Please enable image sending for our account and provide the correct API documentation 
for sending images via WhatsApp.

Thank you!
