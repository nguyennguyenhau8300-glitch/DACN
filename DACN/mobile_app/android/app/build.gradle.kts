import java.net.Inet4Address
import java.net.NetworkInterface

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val developmentHosts = runCatching {
    NetworkInterface.getNetworkInterfaces().toList()
        .filter { it.isUp && !it.isLoopback && !it.isVirtual }
        .flatMap { it.inetAddresses.toList() }
        .filterIsInstance<Inet4Address>()
        .filter { it.isSiteLocalAddress }
        .map { it.hostAddress }
        .distinct().sorted().joinToString(",")
}.getOrDefault("")

android {
    namespace = "vn.parkly.parkly_mobile"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    buildFeatures {
        resValues = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "vn.parkly.parkly_mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        resValue("string", "parkly_dev_hosts", "")
    }

    buildTypes {
        debug {
            resValue("string", "parkly_dev_hosts", developmentHosts)
        }
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

// Flutter invokes assembleDebug before installing a debug build. A single ADB
// target can use the same loopback address as the Windows and browser apps.
val adbExecutable = androidComponents.sdkComponents.adb
val forwardParklyBackend by tasks.registering {
    doLast {
        providers.exec {
            commandLine(adbExecutable.get().asFile, "reverse", "--no-rebind", "tcp:8001", "tcp:8001")
            isIgnoreExitValue = true
        }.result.get()
    }
}
tasks.matching { it.name == "assembleDebug" }.configureEach {
    dependsOn(forwardParklyBackend)
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
