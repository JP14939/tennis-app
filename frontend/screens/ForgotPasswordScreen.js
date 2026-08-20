import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity,
  StyleSheet, SafeAreaView, KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import Alert from '../utils/alert';
import { useAuth } from '../context/AuthContext';
import { playTapSound } from '../utils/sounds';
import { colors, fonts, radius, spacing } from '../theme';

export default function ForgotPasswordScreen({ navigation }) {
  const { forgotPassword } = useAuth();
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit() {
    setError('');
    if (!email) {
      setError('Please enter your email.');
      return;
    }
    setLoading(true);
    try {
      await forgotPassword(email);
      // Same message regardless of whether the account exists -- the
      // backend's response never reveals that either, see AuthContext.js's
      // forgotPassword() comment.
      Alert.alert(
        'Check your inbox',
        "If that email has a RallyMax account, we've sent a link to reset your password.",
        [{ text: 'OK', onPress: () => navigation.goBack() }]
      );
    } catch (err) {
      setError(err.message || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={s.safe}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={s.flex}>
        <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">

          <View style={s.header}>
            <Text style={s.title}>Reset your password</Text>
            <Text style={s.sub}>Enter your account email and we'll send you a reset link.</Text>
          </View>

          <View style={s.form}>
            <View style={s.field}>
              <Text style={s.label}>Email</Text>
              <TextInput
                style={s.input}
                placeholder="you@example.com"
                placeholderTextColor={colors.muted}
                keyboardType="email-address"
                autoCapitalize="none"
                autoComplete="email"
                value={email}
                onChangeText={setEmail}
              />
            </View>

            {error ? <Text style={s.error}>{error}</Text> : null}

            <TouchableOpacity
              style={[s.btnPrimary, loading && s.btnDisabled]}
              onPress={() => { playTapSound(); handleSubmit(); }}
              disabled={loading}
            >
              <Text style={s.btnPrimaryText}>{loading ? 'Sending...' : 'Send reset link'}</Text>
            </TouchableOpacity>

            <TouchableOpacity style={s.backWrap} onPress={() => navigation.goBack()}>
              <Text style={s.back}>Back to log in</Text>
            </TouchableOpacity>
          </View>

        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  scroll: { flexGrow: 1, padding: spacing.xxl },

  header: { alignItems: 'center', marginBottom: 40, marginTop: 20 },
  title: { color: colors.ink, fontSize: 28, fontFamily: fonts.serifItalic, marginBottom: 10, textAlign: 'center' },
  sub: { color: colors.muted, fontSize: 15, fontFamily: fonts.regular, textAlign: 'center' },

  form: { gap: spacing.lg },
  field: { gap: spacing.xs },
  label: { color: colors.mutedDark, fontSize: 13, fontFamily: fonts.semibold },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    padding: 14,
    color: colors.ink,
    fontSize: 15,
    fontFamily: fonts.regular,
  },

  error: { color: colors.coral, fontSize: 13, textAlign: 'center', fontFamily: fonts.semibold },

  btnPrimary: {
    backgroundColor: colors.primary,
    borderRadius: radius.sm,
    padding: 15,
    alignItems: 'center',
    marginTop: 4,
  },
  btnDisabled: { opacity: 0.6 },
  btnPrimaryText: { color: colors.white, fontSize: 16, fontFamily: fonts.bold },

  backWrap: { alignItems: 'center', marginTop: 4 },
  back: { color: colors.muted, fontSize: 13, fontFamily: fonts.regular },
});
