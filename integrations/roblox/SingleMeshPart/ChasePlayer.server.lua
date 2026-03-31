-- Place as child of a MeshPart — 첫 번째 접속 플레이어 HumanoidRootPart 추적 (XZ 평면)

local part = script.Parent
if not part:IsA("MeshPart") and not part:IsA("BasePart") then
	warn("[ChasePlayer] Parent must be MeshPart or BasePart")
	return
end

part.Anchored = false
part.CanCollide = true

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local speed = 12

RunService.Heartbeat:Connect(function()
	local plist = Players:GetPlayers()
	local p = plist[1]
	local char = p and p.Character
	local hrp = char and char:FindFirstChild("HumanoidRootPart")
	if not hrp or not hrp:IsA("BasePart") then
		return
	end

	local dir = (hrp.Position - part.Position) * Vector3.new(1, 0, 1)
	if dir.Magnitude < 0.05 then
		return
	end
	dir = dir.Unit

	part.AssemblyLinearVelocity = Vector3.new(
		dir.X * speed,
		part.AssemblyLinearVelocity.Y,
		dir.Z * speed
	)
	part.CFrame = CFrame.lookAt(part.Position, part.Position + dir)
end)
