# Quiz — AWS Direct Connect

Test yourself: 5 questions, answers hidden below. No peeking!

---

## Questions

**1.** Your on-premises router advertises `10.0.0.0/8` to AWS over a private VIF, but EC2 instances in the VPC can't reach on-prem servers. The BGP session shows `up`. Name **two** things you would check first.

**2.** You need to connect **12 VPCs across 3 regions** to one on-premises data centre over a single Direct Connect connection. Which VIF type and which gateway do you use — and why can't a private VIF do this job?

**3.** A fibre cut takes down your only Direct Connect connection for 40 minutes. Traffic fails over to the Site-to-Site VPN, but the first 90 seconds of the outage are a black hole. What mechanism would have detected the dead path in under a second, and why didn't BGP alone catch it fast enough?

**4.** Your security team says the Direct Connect link carries sensitive database replication traffic. Is the traffic encrypted on the wire by default? If not, name **two** ways to encrypt it.

**5.** Your monthly AWS egress is 800 GB and you are considering a dedicated 1 Gbps Direct Connect connection. The port costs ~$0.30/hour and DX egress is ~$0.02/GB vs ~$0.09/GB over the internet. Does DX save you money at this volume? Show the rough maths — and name one non-cost reason to choose DX anyway.

---

## Answers

<details>
<summary><strong>Click to reveal answers</strong></summary>

**1.** BGP being `up` only proves the peering works — it doesn't prove the *routes* are usable. Check (a) **route propagation on the VPC route table**: the VGW must propagate the on-prem prefix (`10.0.0.0/8`) into the subnet route tables — if propagation is off, the return path doesn't exist; and (b) **security groups / NACLs and the on-prem firewall**: the EC2 security group must allow the traffic, and the on-prem router must have a route back to the VPC CIDR (172.31.0.0/16). Also verify the prefix is actually in the BGP advertised routes, not filtered by a prefix list.

**2.** Use a **transit VIF** attached to a **Direct Connect Gateway**. The DX Gateway fans one connection out to many VPCs (via VGW attachments) in the same or different regions. A private VIF can't do this because it attaches to **one** Virtual Private Gateway — one VPC, one region. (Also note the DX Gateway limit: up to 3 DX Gateways per transit VIF, and route limits apply.)

**3.** **BFD — Bidirectional Forwarding Detection.** BGP's default hold timers take 30–90 seconds to declare a peer dead, so traffic keeps being sent into the dead path until the timer expires. BFD runs fast hello packets (sub-second) between the two routers and tells BGP immediately when the path dies, so failover starts in under a second. Enable it on both the customer router and the AWS side.

**4.** **No — Direct Connect is private, not encrypted.** The fibre runs through a colocation facility, not the public internet, but the bits are in the clear. Two ways to encrypt: (1) **MACsec** — line-rate encryption on supported dedicated connections (keys exchanged via CKN/CAK); (2) **VPN over Direct Connect** — run an IPsec Site-to-Site VPN tunnel on top of the private VIF, so you keep the private path *and* get encryption.

**5.** Rough maths: port = 0.30 × 730 h ≈ **$219/month**. DX egress = 800 × 0.02 = **$16**. DX total ≈ **$235**. Internet egress = 800 × 0.09 = **$72**. So no — at 800 GB/month DX costs about **$163/month more**; the egress discount ($56 saved) doesn't cover the port. Break-even is roughly 3 TB/month of egress. Non-cost reasons to choose DX anyway: **stable, predictable latency** (no internet congestion/jitter) and a **private path** for latency-sensitive or compliance-driven workloads — plus it scales: the same port serves far more traffic later without re-architecting.

</details>
