using OriginReal.Integration.Runtime;
using UnityEditor;
using UnityEngine;

namespace OriginReal.Integration.Editor
{
    /// <summary>
    /// 메뉴에서 선택 오브젝트에 컴포넌트 일괄 부착 (Rigidbody 없으면 추가).
    /// Unity 프로젝트에 이 폴더를 Assets 하위로 복사한 뒤 사용.
    /// </summary>
    public static class AttachBehaviorMenu
    {
        static void EnsureRigidbody(GameObject go)
        {
            if (go.GetComponent<Rigidbody>() == null)
            {
                Undo.AddComponent<Rigidbody>(go);
            }
        }

        [MenuItem("Tools/Origin Real/Attach/Roll Forward")]
        static void AttachRoll()
        {
            foreach (var go in Selection.gameObjects)
            {
                Undo.RecordObject(go, "Add RollForward");
                EnsureRigidbody(go);
                if (go.GetComponent<RollForward>() == null)
                    Undo.AddComponent<RollForward>(go);
            }
        }

        [MenuItem("Tools/Origin Real/Attach/Chase Player")]
        static void AttachChase()
        {
            foreach (var go in Selection.gameObjects)
            {
                Undo.RecordObject(go, "Add ChasePlayer");
                EnsureRigidbody(go);
                if (go.GetComponent<ChasePlayer>() == null)
                    Undo.AddComponent<ChasePlayer>(go);
            }
        }

        [MenuItem("Tools/Origin Real/Attach/Simple Wheel Torque (needs wheel Rigidbody)")]
        static void AttachWheelTorque()
        {
            foreach (var go in Selection.gameObjects)
            {
                Undo.RecordObject(go, "Add SimpleWheelTorque");
                if (go.GetComponent<SimpleWheelTorque>() == null)
                    Undo.AddComponent<SimpleWheelTorque>(go);
            }
        }

        [MenuItem("Tools/Origin Real/Attach/Roll Forward", true)]
        [MenuItem("Tools/Origin Real/Attach/Chase Player", true)]
        [MenuItem("Tools/Origin Real/Attach/Simple Wheel Torque (needs wheel Rigidbody)", true)]
        static bool ValidateSelection() => Selection.gameObjects.Length > 0;
    }
}
