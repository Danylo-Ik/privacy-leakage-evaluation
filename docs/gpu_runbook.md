# GPU runbook: vast.ai + vLLM, step by step

The exact sequence that worked for generating the corpus. Background, team rules and the reasons behind each setting are in `docs/gpu_setup.md`.

Commands are meant to be copied as they are. Values that change per instance are set once as shell variables (step 4), so there is nothing to edit inside the commands. Lines starting with `#` are comments.

Where each command runs:

- **[laptop]**: a terminal on your own computer, in the repo folder
- **[server]**: inside the SSH session on the vast.ai instance
- **[console]**: the vast.ai website

---

## 0. Once per person: SSH key

**[laptop]** Check whether you already have a key:

```
ls ~/.ssh/id_ed25519.pub
```

If the file is missing, create one (a passphrase is optional but recommended):

```
ssh-keygen -t ed25519
```

Copy the public key and send it to the person holding the credit, or add it yourself in step 2:

```
pbcopy < ~/.ssh/id_ed25519.pub
```

If your key has a passphrase, load it into the macOS agent once, so tunnels and scripts can use it without asking:

```
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
```

## 1. Once per session: Hugging Face token

**[browser]**

1. Accept the license at huggingface.co/google/gemma-4-31B-it ("Agree and access repository").
2. Settings → Access Tokens → Create new token → **Fine-grained**, tick only "Read access to contents of all public gated repos you can access". Copy the `hf_...` token.

**[laptop]** Optional check before paying for a GPU (prints `200` if the token works):

```
read -s HF_TOKEN; export HF_TOKEN
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $HF_TOKEN" \
  https://huggingface.co/google/gemma-4-31B-it/resolve/main/config.json
```

The token only ever goes into the server's shell (step 5). Not into `.env`, the repo, the instance settings or chats.

## 2. [console] SSH keys, before renting

1. Switch to your **personal** view with the context switcher in the top-left. (If Keys says "SSH Keys are only available in personal context", you are still in the team view.)
2. Keys → SSH Keys → add the public key of everyone who needs access.

Keys are copied only to instances created after this step.

## 3. [console] Rent the instance

1. Switch back to the **team** view.
2. Search with these filters: 1× **A100 80GB** or **H100 80GB**, reliability ≥ 98%, download ≥ 500 Mbps, max CUDA ≥ 12.8. Check the hourly price including storage.
3. Edit image & config:
   - Image: `vllm/vllm-openai:v0.33.0`
   - Launch mode: **SSH**
   - Docker options, environment variables, on-start script: **leave empty**
   - Disk: **120 GB**
   - Label: your group name + "do not stop"
4. Rent. Wait until the status is **Running**, then open **Connect** and note the **direct** command, e.g. `ssh -p 34099 root@203.0.113.7`.

## 4. [laptop] Save the connection details

Take the port and IP from the direct command:

```
export VAST_PORT=34099
export VAST_IP=203.0.113.7
```

These variables only live in the current terminal. Set them again in a new one.

## 5. [server] Start vLLM

Log in:

```
ssh -p $VAST_PORT root@$VAST_IP
```

The first time, answer `yes` to the host-key question. You land in a tmux session.

Check the machine:

```
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
df -h /root | tail -1
vllm --version
```

Expect one A100/H100 with about 80 GB, about 120 GB of disk, and vLLM 0.33.0.

Set the two keys. Paste the Hugging Face token after the first line and press Enter; nothing is shown:

```
read -s HF_TOKEN; export HF_TOKEN
export VLLM_API_KEY=$(openssl rand -hex 24)
echo $VLLM_API_KEY
```

Copy the printed `VLLM_API_KEY`; it goes into `.env` in step 6 and to teammates privately.

Start the server:

```
nohup vllm serve google/gemma-4-31B-it \
  --max-model-len 16384 --gpu-memory-utilization 0.92 \
  --reasoning-parser gemma4 --api-key "$VLLM_API_KEY" \
  --host 127.0.0.1 --port 8000 > /root/vllm.log 2>&1 &

tail -f /root/vllm.log
```

Wait for `Application startup complete` (10–20 minutes the first time: the model downloads). Then:

- **Ctrl+C** stops watching the log. The server keeps running.
- **Ctrl+b, then d** detaches from tmux and closes the SSH session. Everything keeps running.

## 6. [laptop] Point the code at the server

Edit `.env` in the repo root (it is gitignored) so it contains:

```
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=google/gemma-4-31B-it
LLM_API_KEY=paste-the-VLLM_API_KEY-here
LLM_MAX_TOKENS=8000
```

Remove or comment out `LLM_NO_SYSTEM` and `LLM_MIN_INTERVAL` if they are there (they are only for Google's free API).

## 7. [laptop] Open the tunnel

In its own terminal tab (set `VAST_PORT` and `VAST_IP` there too), and leave it open:

```
ssh -N -L 8000:localhost:8000 -p $VAST_PORT root@$VAST_IP
```

It prints nothing while it works.

## 8. [laptop] Check and run

In another tab, in the repo folder:

```
python3 data_understanding/llm.py ping
```

Expected: the model name and a one-sentence Ukrainian answer.

Then, for example:

```
python3 data_understanding/generate.py data/sample --limit 3 --workers 3
python3 data_understanding/generate.py data/sample --workers 8
python3 data_understanding/generate.py data/full --workers 8
python3 data_understanding/checks.py data/full
```

On one A100: 30 documents took about 2.5 minutes, 150 took 12 minutes.

## 9. Stopping

**[laptop]** Close the tunnel: Ctrl+C in its tab.

**[console]** Team view → Instances → your instance:

- **Stop**: GPU billing stops, disk is still billed, the model stays on disk. After a restart, repeat steps 4–7 (the port may change; the download is skipped).
- **Destroy**: everything stops and is deleted. Next time, start again from step 3.

Never leave an instance running overnight. Only stop or destroy your own, labelled instance.

**[browser]** When the session is over, delete the Hugging Face token.

---

## Problems we hit, and the fix

| Symptom | Cause | Fix |
|---|---|---|
| `zsh: parse error near '\n'` | `<port>`-style placeholders typed literally | use the variables from step 4 |
| `Permission denied (publickey)` | your key was added after the instance was created | add the key on the running instance (console, or a line in `/root/.ssh/authorized_keys`); check with the commands below |
| works in your terminal but not from scripts | the key has a passphrase that scripts can't type | `ssh-add --apple-use-keychain ~/.ssh/id_ed25519` |
| `SSH Keys are only available in personal context` | you are in the team view | switch to your personal view for keys, back to the team view to rent |
| `ping` gives 404 | wrong model name for that endpoint | on vLLM the name is `google/gemma-4-31B-it`; list models with the command below |
| reply starts with `<thought>` or is empty | Gemma 4 thinks first and the thinking used up the tokens | keep `--reasoning-parser gemma4` and `LLM_MAX_TOKENS=8000` |
| vLLM log shows 401 / gated repo | license not accepted or token without gated-repo access | redo step 1 |
| vLLM log shows CUDA out of memory | context too long for the card | restart with `--max-model-len 12288` (or `--quantization fp8` on an H100) |
| `ping` can't connect | tunnel closed or server stopped | reopen step 7; on the server, `tail /root/vllm.log` |

Check which key SSH offers and whether the server accepts it:

```
ssh -v -o BatchMode=yes -p $VAST_PORT root@$VAST_IP true 2>&1 | grep -E "Offering|accepts|denied"
ssh-keygen -lf ~/.ssh/id_ed25519.pub
```

List the models the endpoint serves (through the tunnel):

```
python3 -c "import sys; sys.path.insert(0,'data_understanding'); import llm, openai; c=llm.settings(); print([m.id for m in openai.OpenAI(base_url=c['base_url'], api_key=c['api_key']).models.list()])"
```
