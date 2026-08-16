import { useEffect, useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, Switch, Alert,
  StyleSheet, SafeAreaView, ScrollView,
} from 'react-native';
import { useAuth } from '../context/AuthContext';
import { changePassword } from '../api/account';
import { colors, fonts, radius, spacing } from '../theme';
import { isSoundEnabled, setSoundEnabled, playTapSound } from '../utils/sounds';

function Section({ title, children }) {
  return (
    <View style={sec.wrap}>
      <Text style={sec.title}>{title}</Text>
      {children}
    </View>
  );
}
const sec = StyleSheet.create({
  wrap: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: 16, marginBottom: spacing.lg },
  title: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.bold, marginBottom: 12 },
});

export default function SettingsScreen({ navigation }) {
  const { user, token, updateUser, deleteAccount } = useAuth();

  // ── Display name ──────────────────────────────────────────────────────
  const [name, setName] = useState(user?.name ?? '');
  const [savingName, setSavingName] = useState(false);

  const saveName = async () => {
    if (!name.trim()) { Alert.alert('Name is required'); return; }
    setSavingName(true);
    try {
      await updateUser({ name: name.trim() });
    } catch (err) {
      Alert.alert('Could not save', err.message || 'Something went wrong');
    } finally {
      setSavingName(false);
    }
  };

  // ── Username ───────────────────────────────────────────────────────────
  const [username, setUsername] = useState(user?.username ?? '');
  const [savingUsername, setSavingUsername] = useState(false);

  const saveUsername = async () => {
    const trimmed = username.trim().toLowerCase();
    if (!/^[a-z0-9_]{3,20}$/.test(trimmed)) {
      Alert.alert('Invalid username', 'Use 3-20 characters: lowercase letters, numbers, or underscores.');
      return;
    }
    setSavingUsername(true);
    try {
      await updateUser({ username: trimmed });
      setUsername(trimmed);
    } catch (err) {
      Alert.alert('Could not save', err.message || 'Something went wrong');
    } finally {
      setSavingUsername(false);
    }
  };

  // ── Push notifications ────────────────────────────────────────────────
  const [notifEnabled, setNotifEnabled] = useState(!!user?.notifications_enabled);

  const toggleNotif = async (value) => {
    setNotifEnabled(value);
    try {
      await updateUser({ notifications_enabled: value });
    } catch (err) {
      setNotifEnabled(!value);
      Alert.alert('Could not update', err.message || 'Something went wrong');
    }
  };

  // ── Sound effects ──────────────────────────────────────────────────────
  // Local device preference, not synced to the backend -- unlike
  // notifications_enabled above, nothing server-side needs to know this.
  const [soundEnabled, setSoundEnabledState] = useState(true);
  useEffect(() => { isSoundEnabled().then(setSoundEnabledState); }, []);

  const toggleSound = async (value) => {
    setSoundEnabledState(value);
    await setSoundEnabled(value);
    if (value) playTapSound(); // immediate feedback that it's back on
  };

  // ── Change password ───────────────────────────────────────────────────
  const [pwOpen, setPwOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changingPw, setChangingPw] = useState(false);

  const submitPasswordChange = async () => {
    if (newPassword.length < 8) {
      Alert.alert('Password too short', 'New password must be at least 8 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      Alert.alert("Passwords don't match");
      return;
    }
    setChangingPw(true);
    try {
      await changePassword(token, { currentPassword, newPassword });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setPwOpen(false);
      Alert.alert('Password changed');
    } catch (err) {
      Alert.alert('Could not change password', err.message || 'Something went wrong');
    } finally {
      setChangingPw(false);
    }
  };

  // ── Delete account ────────────────────────────────────────────────────
  const [delOpen, setDelOpen] = useState(false);
  const [delPassword, setDelPassword] = useState('');
  const [delError, setDelError] = useState('');
  const [deleting, setDeleting] = useState(false);

  const submitDelete = async () => {
    setDelError('');
    setDeleting(true);
    try {
      await deleteAccount(delPassword);
      navigation.popToTop();
    } catch (err) {
      setDelError(err.message || 'Something went wrong');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        <Section title="Display name">
          <TextInput
            style={s.input}
            value={name}
            onChangeText={setName}
            placeholder="Your name"
            placeholderTextColor={colors.muted}
          />
          <TouchableOpacity
            style={[s.saveBtn, (savingName || !name.trim()) && s.saveBtnDisabled]}
            onPress={() => { playTapSound(); saveName(); }}
            disabled={savingName || !name.trim()}
          >
            <Text style={s.saveBtnText}>{savingName ? 'Saving...' : 'Save name'}</Text>
          </TouchableOpacity>
        </Section>

        <Section title="Username">
          <TextInput
            style={s.input}
            value={username}
            onChangeText={(t) => setUsername(t.toLowerCase())}
            placeholder="e.g. rally_max"
            placeholderTextColor={colors.muted}
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Text style={s.switchSub}>Shown to friends and coaches instead of your email. 3-20 characters, lowercase letters, numbers, or underscores.</Text>
          <TouchableOpacity
            style={[s.saveBtn, (savingUsername || !username.trim()) && s.saveBtnDisabled]}
            onPress={() => { playTapSound(); saveUsername(); }}
            disabled={savingUsername || !username.trim()}
          >
            <Text style={s.saveBtnText}>{savingUsername ? 'Saving...' : 'Save username'}</Text>
          </TouchableOpacity>
        </Section>

        <Section title="Notifications">
          <View style={s.switchRow}>
            <View style={{ flex: 1 }}>
              <Text style={s.switchLabel}>Push notifications</Text>
              <Text style={s.switchSub}>Alerts when a highlight job finishes processing</Text>
            </View>
            <Switch
              value={notifEnabled}
              onValueChange={toggleNotif}
              trackColor={{ false: colors.border, true: colors.primary }}
              thumbColor={colors.white}
            />
          </View>
        </Section>

        <Section title="Sound">
          <View style={s.switchRow}>
            <View style={{ flex: 1 }}>
              <Text style={s.switchLabel}>Sound effects</Text>
              <Text style={s.switchSub}>A light tap sound on primary buttons — respects your phone's silent switch</Text>
            </View>
            <Switch
              value={soundEnabled}
              onValueChange={toggleSound}
              trackColor={{ false: colors.border, true: colors.primary }}
              thumbColor={colors.white}
            />
          </View>
        </Section>

        <Section title="Change password">
          <TouchableOpacity style={s.toggleRow} onPress={() => setPwOpen((o) => !o)}>
            <Text style={s.toggleRowText}>{pwOpen ? 'Cancel' : 'Change your password'}</Text>
          </TouchableOpacity>
          {pwOpen && (
            <View style={s.pwForm}>
              <TextInput
                style={s.input}
                value={currentPassword}
                onChangeText={setCurrentPassword}
                placeholder="Current password"
                placeholderTextColor={colors.muted}
                secureTextEntry
              />
              <TextInput
                style={s.input}
                value={newPassword}
                onChangeText={setNewPassword}
                placeholder="New password (min 8 characters)"
                placeholderTextColor={colors.muted}
                secureTextEntry
              />
              <TextInput
                style={s.input}
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                placeholder="Confirm new password"
                placeholderTextColor={colors.muted}
                secureTextEntry
              />
              <TouchableOpacity
                style={[s.saveBtn, changingPw && s.saveBtnDisabled]}
                onPress={submitPasswordChange}
                disabled={changingPw}
              >
                <Text style={s.saveBtnText}>{changingPw ? 'Changing...' : 'Change password'}</Text>
              </TouchableOpacity>
            </View>
          )}
        </Section>

        <View style={[sec.wrap, s.dangerWrap]}>
          <Text style={[sec.title, s.dangerTitle]}>Delete account</Text>
          <TouchableOpacity style={s.toggleRow} onPress={() => { setDelOpen((o) => !o); setDelError(''); }}>
            <Text style={[s.toggleRowText, s.dangerText]}>
              {delOpen ? 'Cancel' : 'Delete my account'}
            </Text>
          </TouchableOpacity>
          {delOpen && (
            <View style={s.pwForm}>
              <Text style={s.dangerWarning}>
                This permanently deletes your analyses, saved history, and highlight clips. This
                can't be undone. Enter your password to confirm.
              </Text>
              <TextInput
                style={s.input}
                value={delPassword}
                onChangeText={setDelPassword}
                placeholder="Password"
                placeholderTextColor={colors.muted}
                secureTextEntry
              />
              {!!delError && <Text style={s.dangerError}>{delError}</Text>}
              <TouchableOpacity
                style={[s.deleteBtn, (deleting || !delPassword) && s.saveBtnDisabled]}
                onPress={submitDelete}
                disabled={deleting || !delPassword}
              >
                <Text style={s.deleteBtnText}>{deleting ? 'Deleting...' : 'Permanently delete my account'}</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 24, paddingBottom: 60 },

  input: {
    backgroundColor: colors.bg, borderRadius: radius.sm, paddingHorizontal: 14, paddingVertical: 12,
    color: colors.ink, fontSize: 14, fontFamily: fonts.regular, marginBottom: 10,
  },
  saveBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 12, alignItems: 'center' },
  saveBtnDisabled: { opacity: 0.4 },
  saveBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },

  switchRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  switchLabel: { color: colors.ink, fontSize: 14, fontFamily: fonts.semibold },
  switchSub: { color: colors.muted, fontSize: 11.5, marginTop: 2, fontFamily: fonts.regular },

  toggleRow: { paddingVertical: 4 },
  toggleRowText: { color: colors.primary, fontSize: 13.5, fontFamily: fonts.bold },
  pwForm: { marginTop: 12 },

  dangerWrap: { borderWidth: 1, borderColor: '#f3d4d0' },
  dangerTitle: { color: colors.coral },
  dangerText: { color: colors.coral },
  dangerWarning: { color: colors.mutedDark, fontSize: 12.5, lineHeight: 18, marginBottom: 12, fontFamily: fonts.regular },
  dangerError: { color: colors.coral, fontSize: 12.5, marginBottom: 10, fontFamily: fonts.semibold },
  deleteBtn: { backgroundColor: colors.coral, borderRadius: radius.pill, paddingVertical: 12, alignItems: 'center' },
  deleteBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },
});
