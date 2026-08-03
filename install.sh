#!/bin/bash

# Music MCP CLI Installer
echo "🎵 Welcome to the Music MCP Installer 🎵"
echo "=========================================="
echo ""

# Ask for email
read -p "Enter your email address to securely request a one-time passcode: " email

if [[ -z "$email" ]]; then
  echo "❌ Email is required."
  exit 1
fi

echo ""
echo "Sending OTP to $email..."
response=$(curl -s -X POST https://music.builditwithai.xyz/api/auth/otp -H "Content-Type: application/json" -d "{\"email\": \"$email\"}")

if [[ "$response" != *"\"success\":true"* ]]; then
  echo "❌ Failed to send OTP. Please try again."
  exit 1
fi

echo "✅ OTP sent successfully!"
echo ""

# Ask for OTP
read -p "Enter the 6-digit OTP from your email: " otp

if [[ -z "$otp" ]]; then
  echo "❌ OTP is required."
  exit 1
fi

echo ""
echo "Verifying OTP..."
verify_response=$(curl -s -X POST https://music.builditwithai.xyz/api/auth/verify -H "Content-Type: application/json" -d "{\"email\": \"$email\", \"otp\": \"$otp\"}")

if [[ "$verify_response" == *"\"error\""* ]]; then
  echo "❌ Invalid or expired OTP. Please try again."
  exit 1
fi

echo "✅ OTP verified!"
echo ""

# Extract API Key (basic string parsing in case jq is not installed)
api_key=$(echo "$verify_response" | grep -o '"api_key":"[^"]*' | cut -d'"' -f4)

if [[ -z "$api_key" ]]; then
  echo "❌ Could not extract API Key."
  exit 1
fi

echo "🎉 Here is your MCP Server Configuration. Copy this block into your Claude Desktop or Antigravity config file:"
echo ""
echo "\"mcpServers\": {"
echo "  \"music-mcp\": {"
echo "    \"command\": \"npx\","
echo "    \"args\": ["
echo "      \"-y\","
echo "      \"@modelcontextprotocol/server-sse\","
echo "      \"--url\","
echo "      \"https://music.builditwithai.xyz/mcp?key=${api_key}\""
echo "    ]"
echo "  }"
echo "}"
echo ""
echo "Happy hacking! 🚀"
