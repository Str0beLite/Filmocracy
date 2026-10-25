-- Explicit deny documents the invitation table's intentional lack of client access.
-- Only private, identity-checked SECURITY DEFINER functions read/write these hashes.
create policy no_client_access on private.session_invites
  for all to authenticated using (false) with check (false);
