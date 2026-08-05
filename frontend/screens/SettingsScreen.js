import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, Switch, Alert,
  StyleSheet, SafeAreaView, ScrollView,
} from 'react-native';
import { useAuth } from '../context/AuthContext';
import { changePassword } from '../api/account';
import { colors, fonts, radius, spacing } from '../theme';

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
            onPress={saveName}
            disabled={savingName || !name.trim()}
          >
            <Text style={s.saveBtnText}>{savingName ? 'Saving...' : 'Save name'}</Text>
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
