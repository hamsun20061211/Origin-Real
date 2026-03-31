-- Place as child of a MeshPart (Script, RunContext = Legacy 또는 Server 권장)
-- 단일 MeshPart: 전방으로 밀기 (Rigidbody 스타일 물리)

local part = script.Parent
if not part:IsA("MeshPart") and not part:IsA("BasePart") then
	warn("[RollForward] Parent must be MeshPart or BasePart, got:", part.ClassName)
	return
end

part.Anchored = false
part.CanCollide = true

local RunService = game:GetService("RunService")
local speed = 20

RunService.Heartbeat:Connect(function()
	local lv = part.CFrame.LookVector
	part.AssemblyLinearVelocity = Vector3.new(
		lv.X * speed,
		part.AssemblyLinearVelocity.Y,
		lv.Z * speed
	)
end)
