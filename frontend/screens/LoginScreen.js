import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, Image,
  StyleSheet, SafeAreaView, KeyboardAvoidingView, Platform, ScrollView, Alert, Linking,
} from 'react-native';
import { useAuth } from '../context/AuthContext';
import { playTapSound } from '../utils/sounds';
import { colors, fonts, radius, spacing } from '../theme';

export default function LoginScreen({ navigation }) {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    setError('');
    if (!email || !password) {
      setError('Please fill in all fields.');
      return;
    }
    setLoading(true);
    try {
      await login(email, password);
      navigation.navigate('MainTabs', { screen: 'Home' });
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
            <Image source={require('../assets/branding/logo-rallymax.png')} style={s.logo} resizeMode="contain" />
            <Text style={s.title}>Welcome back</Text>
            <Text style={s.sub}>Log in to your RallyMax account</Text>
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

            <View style={s.field}>
              <Text style={s.label}>Password</Text>
              <TextInput
                style={s.input}
                placeholder="••••••••"
                placeholderTextColor={colors.muted}
                secureTextEntry
                autoComplete="password"
                value={password}
                onChangeText={setPassword}
              />
            </View>

            {error ? <Text style={s.error}>{error}</Text> : null}

            <TouchableOpacity
              style={[s.btnPrimary, loading && s.btnDisabled]}
              onPress={() => { playTapSound(); handleLogin(); }}
              disabled={loading}
            >
              <Text style={s.btnPrimaryText}>{loading ? 'Logging in...' : 'Log in'}</Text>
            </TouchableOpacity>

            {/* No self-serve password reset flow exists yet -- this used to
                be a dead button with no onPress handler at all. Points to
                support instead of silently doing nothing, until a real
                reset flow (email + token) is built. */}
            <TouchableOpacity
              style={s.forgotWrap}
              onPress={() => Alert.alert(
                'Forgot your password?',
                'Password reset isn\'t self-serve yet — email support@rallymax.app and we\'ll help you back in.',
                [
                  { text: 'Email support', onPress: () => Linking.openURL('mailto:support@rallymax.app') },
                  { text: 'OK', style: 'cancel' },
                ]
              )}
            >
              <Text style={s.forgot}>Forgot password?</Text>
            </TouchableOpacity>
          </View>

          <View style={s.footer}>
            <Text style={s.footerText}>Don't have an account? </Text>
            <TouchableOpacity onPress={() => navigation.navigate('Signup')}>
              <Text style={s.footerLink}>Sign up free</Text>
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

  header: { alignItems: 'center', marginBottom: 40 },
  logo: { width: 140, height: 46, marginBottom: 18 },
  title: { color: colors.ink, fontSize: 32, fontFamily: fonts.serifItalic, marginBottom: 6 },
  sub: { color: colors.muted, fontSize: 15, fontFamily: fonts.regular },

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

  forgotWrap: { alignItems: 'center', marginTop: 4 },
  forgot: { color: colors.muted, fontSize: 13, fontFamily: fonts.regular },

  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 40,
  },
  footerText: { color: colors.muted, fontSize: 14, fontFamily: fonts.regular },
  footerLink: { color: colors.primary, fontSize: 14, fontFamily: fonts.bold },
});
