#include <WiFi.h>
#include <FirebaseESP32.h>

#define WIFI_SSID ""
#define WIFI_PASSWORD ""

#define FIREBASE_HOST ""  // Replace with your Firebase Database URL (without "https://")
#define FIREBASE_AUTH ""   // Get this from Firebase Project Settings > Service accounts > Database secrets  // Get this from Firebase Project Settings > Service accounts > Database secrets

FirebaseData firebaseData;
FirebaseConfig config;
FirebaseAuth auth;

void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to WiFi...");
  }
  Serial.println("Connected to WiFi");

  // Set up Firebase configuration
  config.host = FIREBASE_HOST;
  config.signer.tokens.legacy_token = FIREBASE_AUTH;

  Firebase.begin(&config, &auth);
  Firebase.reconnectWiFi(true);
}

void loop() {
  if (Firebase.ready()) {
    String path = "/sensorData2"; // Path in Firebase Realtime Database

    // Create a FirebaseJson object and set the data
    FirebaseJson jsonData;
    jsonData.set("temperature", random(50, 101));
    jsonData.set("humidity", random(50, 101));

    // Push JSON data to Firebase
    if (Firebase.pushJSON(firebaseData, path, jsonData)) {
      Serial.println("Data sent to Firebase");
    } else {
      Serial.println("Failed to send data: " + firebaseData.errorReason());
    }
  }

  delay(5000); // Send data every 5 seconds
}

