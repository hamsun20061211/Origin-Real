-- Model 루트에 두세요. PrimaryPart 필수. 관절은 Weld로 고정된 '한 덩어리' 추적용.

local model = script.Parent
if not model:IsA("Model") then
	warn("[ChaseUsingPrimaryPart] Parent must be Model")
	return
end

local root = model.PrimaryPart
if not root then
	warn("[ChaseUsingPrimaryPart] Set Model.PrimaryPart (usually main body).")
	return
end

root.Anchored = false
root.CanCollide = true

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

	local dir = (hrp.Position - root.Position) * Vector3.new(1, 0, 1)
	if dir.Magnitude < 0.05 then
		return
	end
	dir = dir.Unit

	root.AssemblyLinearVelocity = Vector3.new(
		dir.X * speed,
		root.AssemblyLinearVelocity.Y,
		dir.Z * speed
	)
	root.CFrame = CFrame.lookAt(root.Position, root.Position + dir)
end)
