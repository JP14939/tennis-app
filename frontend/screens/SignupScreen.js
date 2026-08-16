import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, Image,
  StyleSheet, SafeAreaView, KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import { useAuth } from '../context/AuthContext';
import { playTapSound } from '../utils/sounds';
import { colors, fonts, radius, spacing } from '../theme';

export default function SignupScreen({ navigation }) {
  const { signup } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSignup() {
    setError('');
    if (!name || !email || !password) {
      setError('Please fill in all fields.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    setLoading(true);
    try {
      await signup(email, password, name);
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
            <Text style={s.title}>Create account</Text>
            <Text style={s.sub}>Start analysing your swing for free</Text>
          </View>

          <View style={s.perks}>
            {['2 free swing analyses per day', 'Matched to pro players', 'Personalised coaching tips'].map(p => (
              <View key={p} style={s.perk}>
                <Text style={s.perkCheck}>✓</Text>
                <Text style={s.perkText}>{p}</Text>
              </View>
            ))}
          </View>

          <View style={s.form}>
            <View style={s.field}>
              <Text style={s.label}>Full name</Text>
              <TextInput
                style={s.input}
                placeholder="Roger Federer"
                placeholderTextColor={colors.muted}
                autoCapitalize="words"
                autoComplete="name"
                value={name}
                onChangeText={setName}
              />
            </View>

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
                placeholder="Min. 8 characters"
                placeholderTextColor={colors.muted}
                secureTextEntry
                autoComplete="new-password"
                value={password}
                onChangeText={setPassword}
              />
            </View>

            {error ? <Text style={s.error}>{error}</Text> : null}

            <TouchableOpacity
              style={[s.btnPrimary, loading && s.btnDisabled]}
              onPress={() => { playTapSound(); handleSignup(); }}
              disabled={loading}
            >
              <Text style={s.btnPrimaryText}>{loading ? 'Creating account...' : 'Create free account'}</Text>
            </TouchableOpacity>

            <Text style={s.terms}>
              By signing up you agree to our Terms of Service and Privacy Policy.
            </Text>
          </View>

          <View style={s.footer}>
            <Text style={s.footerText}>Already have an account? </Text>
            <TouchableOpacity onPress={() => navigation.navigate('Login')}>
              <Text style={s.footerLink}>Log in</Text>
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

  header: { alignItems: 'center', marginBottom: 24 },
  logo: { width: 140, height: 46, marginBottom: 18 },
  title: { color: colors.ink, fontSize: 32, fontFamily: fonts.serifItalic, marginBottom: 6 },
  sub: { color: colors.muted, fontSize: 15, fontFamily: fonts.regular },

  perks: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.primarySoft,
    borderRadius: radius.lg,
    padding: 16,
    gap: 10,
    marginBottom: 28,
  },
  perk: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  perkCheck: { color: colors.primary, fontFamily: fonts.bold, fontSize: 15 },
  perkText: { color: colors.mutedDark, fontSize: 14, fontFamily: fonts.regular },

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

  terms: { color: colors.divider, fontSize: 11, textAlign: 'center', lineHeight: 16, fontFamily: fonts.regular },

  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 32,
  },
  footerText: { color: colors.muted, fontSize: 14, fontFamily: fonts.regular },
  footerLink: { color: colors.primary, fontSize: 14, fontFamily: fonts.bold },
});
