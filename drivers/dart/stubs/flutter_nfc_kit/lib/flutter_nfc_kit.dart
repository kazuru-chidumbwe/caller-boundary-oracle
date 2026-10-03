// Compile-time stand-in for flutter_nfc_kit, which needs Flutter. dmrtd's top-level library
// re-exports its NfcProvider, so these declarations must exist for dmrtd to compile; the
// harness never constructs an NfcProvider, so none of this runs. Every member throws.

enum NFCAvailability { not_supported, disabled, available }

enum NFCTagType { iso7816, iso15693, iso18092, mifare_classic, mifare_ultralight, mifare_desfire, mifare_plus, webusb, unknown }

class NFCTag {
  NFCTagType get type => throw UnsupportedError('flutter_nfc_kit stand-in');
}

class FlutterNfcKit {
  static Future<NFCAvailability> get nfcAvailability => throw UnsupportedError('flutter_nfc_kit stand-in');

  static Future<void> setIosAlertMessage(String message) => throw UnsupportedError('flutter_nfc_kit stand-in');

  static Future<NFCTag> poll({Duration? timeout, String? iosAlertMessage, bool? readIso14443A, bool? readIso14443B,
          bool? readIso18092, bool? readIso15693, bool? probeWebUSBMagic, String? iosMultipleTagMessage}) =>
      throw UnsupportedError('flutter_nfc_kit stand-in');

  static Future<void> finish({String? iosAlertMessage, String? iosErrorMessage, bool? closeWebUSB}) =>
      throw UnsupportedError('flutter_nfc_kit stand-in');

  static Future<T> transceive<T>(T capdu, {Duration? timeout}) => throw UnsupportedError('flutter_nfc_kit stand-in');
}
